"""Detect known corpse sprites and estimate their tile offsets from the player."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autoloot.read_world_targets import read_world_targets  # noqa: E402
from autoloot.approach_plan import plan_to_adjacent  # noqa: E402


TEMPLATES = {
    "Amazon": "AmazonDeadLoot.png",
    "Valkyrie": "ValkyrieDeadLoot.png",
    "Witch": "WitchDeadbodyLoot.png",
}


def candidate_matches(
    viewport_image,
    template_image,
    viewport_origin: tuple[int, int],
    tile_size: tuple[float, float],
    threshold: float,
) -> list[dict]:
    candidates = []
    base_size = (tile_size[0] + tile_size[1]) / 2
    sizes = sorted({round(base_size * factor) for factor in (0.9, 0.95, 1.0, 1.05, 1.1)})
    for size in sizes:
        template = cv2.resize(template_image, (size, size), interpolation=cv2.INTER_AREA)
        scores = cv2.matchTemplate(viewport_image, template, cv2.TM_CCOEFF_NORMED)
        work = scores.copy()
        while True:
            _minimum, score, _min_location, location = cv2.minMaxLoc(work)
            if score < threshold:
                break
            x, y = location
            candidates.append(
                {
                    "score": round(float(score), 4),
                    "size": size,
                    "top_left": [x + viewport_origin[0], y + viewport_origin[1]],
                    "center": [
                        x + viewport_origin[0] + size // 2,
                        y + viewport_origin[1] + size // 2,
                    ],
                }
            )
            radius = max(8, size // 3)
            work[
                max(0, y - radius) : min(work.shape[0], y + radius + 1),
                max(0, x - radius) : min(work.shape[1], x + radius + 1),
            ] = -1

    candidates.sort(key=lambda item: item["score"], reverse=True)
    deduplicated = []
    duplicate_radius = base_size * 0.45
    for candidate in candidates:
        if any(
            (candidate["center"][0] - kept["center"][0]) ** 2
            + (candidate["center"][1] - kept["center"][1]) ** 2
            < duplicate_radius**2
            for kept in deduplicated
        ):
            continue
        deduplicated.append(candidate)
    return deduplicated


def detect_corpses(
    image_path: Path,
    expected_counts: dict[str, int],
    templates_folder: Path | None = None,
    threshold: float = 0.55,
) -> dict:
    world = read_world_targets(image_path)
    viewport = world["viewport"]
    player_center = world["player"]["name_center"]
    tile_width, tile_height = world["estimated_tile_size"]
    templates_folder = templates_folder or PROJECT_ROOT / "DeadBodys"

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Nao foi possivel abrir screenshot: {image_path}")
    viewport_image = image[viewport[1] : viewport[3], viewport[0] : viewport[2]]

    detections = []
    for creature, expected_count in expected_counts.items():
        template_name = TEMPLATES.get(creature)
        if template_name is None:
            raise RuntimeError(f"Nao existe template configurado para {creature}")
        template_path = templates_folder / template_name
        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if template is None:
            raise RuntimeError(f"Template nao encontrado: {template_path}")
        candidates = candidate_matches(
            viewport_image,
            template,
            (viewport[0], viewport[1]),
            (tile_width, tile_height),
            threshold,
        )
        for candidate in candidates[:expected_count]:
            dx = round((candidate["center"][0] - player_center[0]) / tile_width)
            dy = round((candidate["center"][1] - player_center[1]) / tile_height)
            detections.append(
                {
                    "creature": creature,
                    **candidate,
                    "tile_offset_from_player": [dx, dy],
                    "approach": plan_to_adjacent([dx, dy]),
                }
            )

    return {
        "image": str(image_path.resolve()),
        "player": world["player"],
        "viewport": viewport,
        "expected_counts": expected_counts,
        "threshold": threshold,
        "detections": detections,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--creature", choices=tuple(TEMPLATES), required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args()

    result = detect_corpses(
        args.image,
        {args.creature: max(0, args.count)},
        threshold=args.threshold,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
