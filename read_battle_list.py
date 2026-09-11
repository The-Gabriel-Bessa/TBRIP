"""Read visible entries and selected enemy names from Tibia's Battle List."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output


DEFAULT_TARGETS = ("Amazon", "Valkyrie", "Witch")


def normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", ascii_text.casefold())


def longest_true_run(values: np.ndarray) -> int:
    padded = np.pad(values.astype(np.int8), (1, 1))
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return int((ends - starts).max()) if len(starts) else 0


def count_visible_entries(roi: Image.Image) -> int:
    pixels = np.asarray(roi.convert("RGB"), dtype=np.uint8)
    red = pixels[:, :, 0].astype(np.int16)
    green = pixels[:, :, 1].astype(np.int16)
    blue = pixels[:, :, 2].astype(np.int16)
    health_color = (
        ((green >= 140) & (green >= red + 50) & (green >= blue + 50))
        | ((red >= 140) & (green >= 100) & (blue <= 100))
        | ((red >= 140) & (red >= green + 50) & (red >= blue + 50))
    )
    bar_rows = [y for y, row in enumerate(health_color) if longest_true_run(row) >= 3]
    if not bar_rows:
        return 0
    groups = []
    current_group = [bar_rows[0]]
    for previous, current in zip(bar_rows, bar_rows[1:]):
        if current > previous + 1:
            groups.append(current_group)
            current_group = []
        current_group.append(current)
    groups.append(current_group)
    return sum(len(group) >= 2 for group in groups)


def read_battle_list(image_path: Path, targets: tuple[str, ...] = DEFAULT_TARGETS) -> dict:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    if width < 1000:
        raise RuntimeError("A captura nao inclui a interface completa")

    box = (
        round(width * 0.86),
        round(height * 0.58),
        width,
        round(height * 0.79),
    )
    roi = image.crop(box)
    visible_entries = count_visible_entries(roi)
    if visible_entries == 0:
        return {
            "image": str(image_path.resolve()),
            "visible_entries": 0,
            "empty": True,
            "targets": list(targets),
            "matched_enemies": [],
            "ocr_tokens": [],
            "region": list(box),
        }

    scale = 4
    enlarged = roi.resize((roi.width * scale, roi.height * scale))
    data = pytesseract.image_to_data(enlarged, config="--psm 6", output_type=Output.DICT)

    tokens = []
    enemies = []
    normalized_targets = {normalize(target): target for target in targets}
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        if not text:
            continue
        confidence = float(data["conf"][index])
        x = box[0] + data["left"][index] // scale
        y = box[1] + data["top"][index] // scale
        token_width = max(1, data["width"][index] // scale)
        token_height = max(1, data["height"][index] // scale)
        token = {
            "text": text,
            "confidence": round(confidence, 1),
            "box": [x, y, token_width, token_height],
        }
        tokens.append(token)

        normalized = normalize(text)
        if not normalized:
            continue
        best_key = max(
            normalized_targets,
            key=lambda target: SequenceMatcher(None, normalized, target).ratio(),
        )
        similarity = SequenceMatcher(None, normalized, best_key).ratio()
        if similarity < 0.8 or (similarity < 1.0 and confidence < 20):
            continue
        enemies.append(
            {
                "name": normalized_targets[best_key],
                "ocr_text": text,
                "confidence": round(confidence, 1),
                "similarity": round(similarity, 2),
                "screenshot_click": [x + token_width // 2, y + token_height // 2],
            }
        )

    return {
        "image": str(image_path.resolve()),
        "visible_entries": visible_entries,
        "empty": visible_entries == 0,
        "targets": list(targets),
        "matched_enemies": enemies,
        "ocr_tokens": tokens,
        "region": list(box),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", type=Path, help="Screenshot completo do Tibia")
    parser.add_argument("--targets", nargs="+", default=list(DEFAULT_TARGETS))
    args = parser.parse_args()

    image_path = args.image
    if image_path is None:
        capture_dir = Path(__file__).resolve().parent / "internal_captures"
        files = list(capture_dir.glob("*.png"))
        if not files:
            raise RuntimeError("Nenhuma captura interna encontrada")
        image_path = max(files, key=lambda path: path.stat().st_mtime_ns)

    result = read_battle_list(image_path, tuple(args.targets))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
