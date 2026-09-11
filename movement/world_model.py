"""Build and query a local cave map from Tibia's minimap and gameplay view."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autoloot.read_world_targets import read_world_targets  # noqa: E402
from movement.zoom_minimap import locate_minimap  # noqa: E402


CAVE_PROFILE = "amazon_camp_cave"
MINIMAP_TILE_SIZE = 4
GAMEPLAY_TILE_SIZE = 44
GAMEPLAY_COLUMNS = 15
GAMEPLAY_ROWS = 11
RIGHT_INTERFACE_WIDTH = 352
GAMEPLAY_CENTER_Y = 302

TERRAIN_COLORS = {
    "walkable_green": (0, 204, 0),
    "blocked_gray": (102, 102, 102),
    "blocked_red": (255, 51, 0),
    "stairs_up_yellow": (255, 255, 0),
}

NAVIGATION = {
    "walkable_green": "walkable",
    "blocked_gray": "blocked",
    "blocked_red": "blocked",
    "stairs_up_yellow": "click_transition",
    "player": "walkable",
    "unknown": "blocked",
}


def coordinate_key(coordinate: tuple[int, int, int]) -> str:
    return ",".join(str(value) for value in coordinate)


def parse_coordinate(key: str) -> tuple[int, int, int]:
    x, y, z = key.split(",")
    return int(x), int(y), int(z)


def find_player_marker(pixels: np.ndarray, minimap_box: list[int]) -> dict:
    white = np.all(pixels == (255, 255, 255), axis=2)
    # OBS converts RGB through YUV, so white commonly returns around 235.
    channel_spread = pixels.max(axis=2).astype(np.int16) - pixels.min(axis=2).astype(np.int16)
    white |= (pixels.min(axis=2) >= 210) & (channel_spread <= 20)
    count, _labels, stats, centers = cv2.connectedComponentsWithStats(white.astype(np.uint8), 8)
    image_center = np.array([(pixels.shape[1] - 1) / 2, (pixels.shape[0] - 1) / 2])
    candidates = []
    for index in range(1, count):
        x, y, width, height, area = (int(value) for value in stats[index])
        if not (12 <= area <= 40 and 4 <= width <= 8 and 4 <= height <= 8):
            continue
        center = centers[index]
        candidates.append((float(np.linalg.norm(center - image_center)), x, y, width, height, area, center))
    if not candidates:
        raise RuntimeError("Ponto branco do personagem nao encontrado no minimapa")

    _distance, x, y, width, height, area, center = min(candidates, key=lambda item: item[0])
    center_x, center_y = float(center[0]), float(center[1])
    tile_left = round(center_x - (MINIMAP_TILE_SIZE - 1) / 2)
    tile_top = round(center_y - (MINIMAP_TILE_SIZE - 1) / 2)
    return {
        "color": "white",
        "component_box": [
            minimap_box[0] + x,
            minimap_box[1] + y,
            width,
            height,
        ],
        "component_area": area,
        "minimap_center": [round(center_x, 2), round(center_y, 2)],
        "screenshot_center": [
            round(minimap_box[0] + center_x, 2),
            round(minimap_box[1] + center_y, 2),
        ],
        "tile_box_in_minimap": [tile_left, tile_top, MINIMAP_TILE_SIZE, MINIMAP_TILE_SIZE],
    }


def classify_tile(tile: np.ndarray) -> tuple[str, int]:
    values = tile.astype(np.int16)
    counts = {}
    for terrain, color in TERRAIN_COLORS.items():
        difference = values - np.asarray(color, dtype=np.int16)
        counts[terrain] = int((np.linalg.norm(difference, axis=2) <= 60).sum())
    terrain, pixels = max(counts.items(), key=lambda item: item[1])
    if pixels < tile.shape[0] * tile.shape[1] // 2:
        return "unknown", pixels
    return terrain, pixels


def read_minimap_tiles(image_path: Path) -> dict:
    minimap = locate_minimap(image_path)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        pixels = np.asarray(image.crop(tuple(minimap["box"])), dtype=np.uint8)

    marker = find_player_marker(pixels, minimap["box"])
    tile_left, tile_top, tile_size, _height = marker["tile_box_in_minimap"]
    tiles: dict[tuple[int, int, int], dict] = {}
    minimum_dx = -(tile_left // tile_size)
    minimum_dy = -(tile_top // tile_size)
    maximum_dx = (pixels.shape[1] - tile_left) // tile_size - 1
    maximum_dy = (pixels.shape[0] - tile_top) // tile_size - 1

    for dy in range(minimum_dy, maximum_dy + 1):
        for dx in range(minimum_dx, maximum_dx + 1):
            left = tile_left + dx * tile_size
            top = tile_top + dy * tile_size
            tile = pixels[top : top + tile_size, left : left + tile_size]
            terrain, matching_pixels = classify_tile(tile)
            if dx == 0 and dy == 0:
                # The white/yellow player marker hides the terrain at the origin.
                terrain = "player"
                matching_pixels = marker["component_area"]
            tiles[(dx, dy, 0)] = {
                "terrain": terrain,
                "navigation": NAVIGATION[terrain],
                "matching_pixels": matching_pixels,
                "minimap_box": [
                    minimap["box"][0] + left,
                    minimap["box"][1] + top,
                    tile_size,
                    tile_size,
                ],
            }

    return {
        "minimap": minimap,
        "tile_size": tile_size,
        "grid_phase": [tile_left % tile_size, tile_top % tile_size],
        "visible_range": {
            "x": [minimum_dx, maximum_dx],
            "y": [minimum_dy, maximum_dy],
            "z": [0, 0],
        },
        "player_marker": marker,
        "tiles": tiles,
    }


def gameplay_point(gameplay_center: list[int], coordinate: tuple[int, int, int]) -> list[int] | None:
    x, y, z = coordinate
    if z != 0 or abs(x) > GAMEPLAY_COLUMNS // 2 or abs(y) > GAMEPLAY_ROWS // 2:
        return None
    return [
        gameplay_center[0] + x * GAMEPLAY_TILE_SIZE,
        gameplay_center[1] + y * GAMEPLAY_TILE_SIZE,
    ]


def locate_gameplay(image_path: Path, player_name: str, verify_name: bool = True) -> dict:
    with Image.open(image_path) as image:
        width, height = image.size
    center = [round((width - RIGHT_INTERFACE_WIDTH) / 2), GAMEPLAY_CENTER_Y]
    half_width = GAMEPLAY_COLUMNS * GAMEPLAY_TILE_SIZE // 2
    half_height = GAMEPLAY_ROWS * GAMEPLAY_TILE_SIZE // 2
    result = {
        "grid_box": [
            center[0] - half_width,
            center[1] - half_height,
            center[0] + half_width,
            center[1] + half_height,
        ],
        "center": center,
        "tile_size": [GAMEPLAY_TILE_SIZE, GAMEPLAY_TILE_SIZE],
        "visible_range": {"x": [-7, 7], "y": [-5, 5], "z": [0, 0]},
        "player_name": {"expected": player_name, "checked": verify_name},
    }
    if not verify_name:
        return result

    world = read_world_targets(image_path, player_name=player_name)
    player = world["player"]
    detected = player["source"] == "ocr"
    delta = [
        player["name_center"][0] - center[0],
        player["name_center"][1] - center[1],
    ]
    result["player_name"].update(
        {
            "detected": detected,
            "source": player["source"],
            "name_center": player["name_center"],
            "offset_from_player_tile": delta,
            "position_consistent": detected
            and abs(delta[0]) <= GAMEPLAY_TILE_SIZE // 2
            and -2 * GAMEPLAY_TILE_SIZE <= delta[1] <= -GAMEPLAY_TILE_SIZE // 3,
        }
    )
    return result


def analyze_world(image_path: Path, player_name: str = "Rafaelkrosa", verify_name: bool = True) -> dict:
    minimap = read_minimap_tiles(image_path)
    gameplay = locate_gameplay(image_path, player_name, verify_name)
    counts = Counter(tile["terrain"] for tile in minimap["tiles"].values())
    stairs = []
    for coordinate, tile in minimap["tiles"].items():
        if tile["terrain"] != "stairs_up_yellow":
            continue
        stairs.append(
            {
                "coordinate": list(coordinate),
                "gameplay_point": gameplay_point(gameplay["center"], coordinate),
                "visible_in_gameplay": gameplay_point(gameplay["center"], coordinate) is not None,
            }
        )
    return {
        "profile": CAVE_PROFILE,
        "image": str(image_path.resolve()),
        "origin": {
            "coordinate": [0, 0, 0],
            "meaning": "current_player_position",
            "minimap_point": minimap["player_marker"]["screenshot_center"],
            "gameplay_point": gameplay["center"],
        },
        "axes": {"x_positive": "east/right", "y_positive": "south/down", "z": "current_floor_is_zero"},
        "minimap": minimap,
        "gameplay": gameplay,
        "terrain_counts": dict(sorted(counts.items())),
        "stairs": stairs,
    }


def reference_tiles(analysis: dict) -> dict[str, str]:
    result = {}
    for coordinate, tile in analysis["minimap"]["tiles"].items():
        if coordinate == (0, 0, 0) or tile["terrain"] == "unknown":
            continue
        result[coordinate_key(coordinate)] = tile["terrain"]
    return result


def make_reference(analysis: dict) -> dict:
    return {
        "version": 1,
        "profile": analysis["profile"],
        "origin": [0, 0, 0],
        "origin_image": analysis["image"],
        "minimap_tile_size": analysis["minimap"]["tile_size"],
        "terrain_colors_rgb": {name: list(color) for name, color in TERRAIN_COLORS.items()},
        "tiles": reference_tiles(analysis),
    }


def localize_in_reference(analysis: dict, reference: dict, minimum_overlap: int = 20) -> dict:
    reference_map = {parse_coordinate(key): terrain for key, terrain in reference["tiles"].items()}
    observed = {
        coordinate: tile["terrain"]
        for coordinate, tile in analysis["minimap"]["tiles"].items()
        if coordinate != (0, 0, 0) and tile["terrain"] != "unknown"
    }
    if not reference_map or not observed:
        raise RuntimeError("Mapa de referencia ou leitura atual sem tiles comparaveis")

    ref_x = [coordinate[0] for coordinate in reference_map]
    ref_y = [coordinate[1] for coordinate in reference_map]
    obs_x = [coordinate[0] for coordinate in observed]
    obs_y = [coordinate[1] for coordinate in observed]
    candidates = []
    for position_y in range(min(ref_y) - max(obs_y), max(ref_y) - min(obs_y) + 1):
        for position_x in range(min(ref_x) - max(obs_x), max(ref_x) - min(obs_x) + 1):
            compared = 0
            matches = 0
            for (dx, dy, _z), terrain in observed.items():
                expected = reference_map.get((position_x + dx, position_y + dy, 0))
                if expected is None:
                    continue
                compared += 1
                matches += expected == terrain
            if compared < minimum_overlap:
                continue
            mismatches = compared - matches
            candidates.append(
                {
                    "coordinate": [position_x, position_y, 0],
                    "compared_tiles": compared,
                    "matching_tiles": matches,
                    "agreement": round(matches / compared, 4),
                    "score": matches - 2 * mismatches,
                }
            )
    if not candidates:
        return {"localized": False, "reason": "insufficient_overlap", "candidates": []}

    candidates.sort(key=lambda item: (item["score"], item["matching_tiles"], item["agreement"]), reverse=True)
    best = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else None
    localized = best["agreement"] >= 0.85 and (second_score is None or best["score"] > second_score)
    return {
        "localized": localized,
        "coordinate": best["coordinate"] if localized else None,
        "best": best,
        "score_margin": None if second_score is None else best["score"] - second_score,
        "candidates": candidates[:5],
    }


def merge_observation(reference: dict, analysis: dict, localization: dict) -> dict:
    if not localization.get("localized"):
        raise RuntimeError("A observacao nao pode ser registrada sem localizacao confiavel")

    position_x, position_y, position_z = localization["coordinate"]
    added = 0
    confirmed = 0
    conflicts = []
    for (dx, dy, dz), tile in analysis["minimap"]["tiles"].items():
        terrain = tile["terrain"]
        if terrain in {"player", "unknown"}:
            continue
        coordinate = (position_x + dx, position_y + dy, position_z + dz)
        key = coordinate_key(coordinate)
        previous = reference["tiles"].get(key)
        if previous is None:
            reference["tiles"][key] = terrain
            added += 1
        elif previous == terrain:
            confirmed += 1
        else:
            conflicts.append(
                {
                    "coordinate": list(coordinate),
                    "reference": previous,
                    "observed": terrain,
                }
            )

    observation = {
        "image": analysis["image"],
        "coordinate": localization["coordinate"],
        "agreement": localization["best"]["agreement"],
        "matching_tiles": localization["best"]["matching_tiles"],
        "added_tiles": added,
        "confirmed_tiles": confirmed,
        "conflicts": len(conflicts),
    }
    observations = reference.setdefault("observations", [])
    if not any(item["image"] == observation["image"] for item in observations):
        observations.append(observation)
        del observations[:-200]
    return {**observation, "conflict_details": conflicts[:10], "total_reference_tiles": len(reference["tiles"])}


def ascii_map(analysis: dict) -> list[str]:
    symbols = {
        "walkable_green": ".",
        "blocked_gray": "#",
        "blocked_red": "R",
        "stairs_up_yellow": "^",
        "player": "P",
        "unknown": "?",
    }
    visible = analysis["minimap"]["visible_range"]
    tiles = analysis["minimap"]["tiles"]
    return [
        "".join(symbols[tiles[(x, y, 0)]["terrain"]] for x in range(visible["x"][0], visible["x"][1] + 1))
        for y in range(visible["y"][0], visible["y"][1] + 1)
    ]


def public_result(analysis: dict) -> dict:
    minimap = analysis["minimap"]
    return {
        "profile": analysis["profile"],
        "image": analysis["image"],
        "origin": analysis["origin"],
        "axes": analysis["axes"],
        "minimap": {
            "box": minimap["minimap"]["box"],
            "tile_size": minimap["tile_size"],
            "grid_phase": minimap["grid_phase"],
            "visible_range": minimap["visible_range"],
            "player_marker": minimap["player_marker"],
        },
        "gameplay": analysis["gameplay"],
        "terrain_counts": analysis["terrain_counts"],
        "stairs": analysis["stairs"],
        "map_legend": {"P": "player", ".": "walkable", "#": "blocked_gray", "R": "blocked_red", "^": "stairs_up", "?": "unknown"},
        "local_map": ascii_map(analysis),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--player", default="Rafaelkrosa")
    parser.add_argument("--initialize-reference", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--update-reference", action="store_true")
    parser.add_argument("--skip-name-check", action="store_true")
    args = parser.parse_args()

    analysis = analyze_world(args.image, args.player, not args.skip_name_check)
    result = public_result(analysis)
    if args.initialize_reference:
        reference = make_reference(analysis)
        args.initialize_reference.parent.mkdir(parents=True, exist_ok=True)
        args.initialize_reference.write_text(json.dumps(reference, indent=2) + "\n", encoding="ascii")
        result["reference_created"] = str(args.initialize_reference.resolve())
        result["reference_tiles"] = len(reference["tiles"])
    if args.reference:
        reference = json.loads(args.reference.read_text(encoding="utf-8"))
        localization = localize_in_reference(analysis, reference)
        result["localization"] = localization
        if args.update_reference:
            result["reference_update"] = merge_observation(reference, analysis, localization)
            args.reference.write_text(json.dumps(reference, indent=2) + "\n", encoding="ascii")
    elif args.update_reference:
        parser.error("--update-reference exige --reference")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
