"""Locate the player and living target names inside the game viewport."""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autoloot.loot_log import clean_line
from read_battle_list import DEFAULT_TARGETS, normalize


def green_name_mask(roi: Image.Image) -> Image.Image:
    pixels = np.asarray(roi.convert("RGB"), dtype=np.uint8)
    red = pixels[:, :, 0].astype(np.int16)
    green = pixels[:, :, 1].astype(np.int16)
    blue = pixels[:, :, 2].astype(np.int16)
    green_names = (green > 120) & (green > red + 50) & (green > blue + 50)
    red_names = (red > 120) & (red > green + 50) & (red > blue + 50)
    yellow_names = (red > 120) & (green > 100) & (blue < 100) & (red > blue + 60)
    selected = green_names | red_names | yellow_names
    return Image.fromarray(np.where(selected, 0, 255).astype(np.uint8))


def read_world_targets(
    image_path: Path,
    player_name: str = "Rafaelkrosa",
    targets: tuple[str, ...] = DEFAULT_TARGETS,
) -> dict:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    if width < 1000:
        raise RuntimeError("A captura nao inclui a interface completa")

    viewport = (
        round(width * 0.10),
        round(height * 0.075),
        round(width * 0.63),
        round(height * 0.80),
    )
    roi = image.crop(viewport)
    roi_pixels = np.asarray(roi, dtype=np.uint8)
    mask = green_name_mask(roi)
    scale = 4
    enlarged = mask.resize((mask.width * scale, mask.height * scale))
    data = pytesseract.image_to_data(enlarged, config="--psm 11", output_type=Output.DICT)

    wanted = {normalize(name): name for name in (*targets, player_name)}
    matches = []
    for index, raw_text in enumerate(data["text"]):
        text = clean_line(raw_text)
        normalized = normalize(text)
        if not normalized:
            continue
        best_key = max(wanted, key=lambda name: SequenceMatcher(None, normalized, name).ratio())
        similarity = SequenceMatcher(None, normalized, best_key).ratio()
        confidence = float(data["conf"][index])
        if similarity < 0.8 or (similarity < 1.0 and confidence < 20):
            continue
        x = viewport[0] + data["left"][index] // scale
        y = viewport[1] + data["top"][index] // scale
        token_width = max(1, data["width"][index] // scale)
        token_height = max(1, data["height"][index] // scale)
        local_x = data["left"][index] // scale
        local_y = data["top"][index] // scale
        token_pixels = roi_pixels[
            local_y : local_y + token_height,
            local_x : local_x + token_width,
        ]
        if token_pixels.size:
            token_red = token_pixels[:, :, 0].astype(np.int16)
            token_green = token_pixels[:, :, 1].astype(np.int16)
            token_blue = token_pixels[:, :, 2].astype(np.int16)
            red_count = int(
                ((token_red > 120) & (token_red > token_green + 50) & (token_red > token_blue + 50)).sum()
            )
            green_count = int(
                ((token_green > 120) & (token_green > token_red + 50) & (token_green > token_blue + 50)).sum()
            )
            yellow_count = int(
                ((token_red > 120) & (token_green > 100) & (token_blue < 100) & (token_red > token_blue + 60)).sum()
            )
            name_color = max(
                ((red_count, "red"), (green_count, "green"), (yellow_count, "yellow")),
                key=lambda item: item[0],
            )[1]
        else:
            name_color = "unknown"
        matches.append(
            {
                "name": wanted[best_key],
                "ocr_text": text,
                "confidence": round(confidence, 1),
                "similarity": round(similarity, 2),
                "name_center": [x + token_width // 2, y + token_height // 2],
                "box": [x, y, token_width, token_height],
                "name_color": name_color,
            }
        )

    player_matches = [match for match in matches if match["name"] == player_name]
    player = max(player_matches, key=lambda match: match["confidence"]) if player_matches else None
    if player is None:
        player_center = [
            (viewport[0] + viewport[2]) // 2,
            (viewport[1] + viewport[3]) // 2,
        ]
        player_source = "viewport_center_fallback"
    else:
        player_center = player["name_center"]
        player_source = "ocr"

    tile_width = (viewport[2] - viewport[0]) / 15.0
    tile_height = (viewport[3] - viewport[1]) / 11.0
    found_targets = []
    for match in matches:
        if match["name"] == player_name:
            continue
        dx = round((match["name_center"][0] - player_center[0]) / tile_width)
        dy = round((match["name_center"][1] - player_center[1]) / tile_height)
        found_targets.append({**match, "tile_offset_from_player": [dx, dy]})

    return {
        "image": str(image_path.resolve()),
        "viewport": list(viewport),
        "estimated_tile_size": [round(tile_width, 2), round(tile_height, 2)],
        "player": {
            "name": player_name,
            "name_center": player_center,
            "source": player_source,
        },
        "targets": found_targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--player", default="Rafaelkrosa")
    parser.add_argument("--targets", nargs="+", default=list(DEFAULT_TARGETS))
    args = parser.parse_args()

    result = read_world_targets(args.image, args.player, tuple(args.targets))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
