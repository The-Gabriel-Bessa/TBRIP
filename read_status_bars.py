"""Read HP and mana percentages from bars in a Tibia built-in screenshot."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


BLACK = np.array([0, 0, 0], dtype=np.uint8)
HEALTH_GREEN = np.array([0, 192, 0], dtype=np.uint8)
MANA_BLUE = np.array([0, 0, 255], dtype=np.uint8)
INNER_WIDTH = 29
OUTER_WIDTH = INNER_WIDTH + 2
BAR_HEIGHT = 2


def find_bars(pixels: np.ndarray, color: np.ndarray) -> list[dict[str, int]]:
    height, width, _ = pixels.shape
    bars = []

    for y in range(1, height - BAR_HEIGHT):
        for x in range(width - OUTER_WIDTH):
            top = pixels[y - 1, x : x + OUTER_WIDTH]
            bottom = pixels[y + BAR_HEIGHT, x : x + OUTER_WIDTH]
            body = pixels[y : y + BAR_HEIGHT, x : x + OUTER_WIDTH]
            if not np.all(top == BLACK) or not np.all(bottom == BLACK):
                continue
            if not np.all(body[:, 0] == BLACK) or not np.all(body[:, -1] == BLACK):
                continue

            inner = body[:, 1:-1]
            colored = np.all(inner == color, axis=2)
            empty = np.all(inner == BLACK, axis=2)
            if not np.all(colored | empty):
                continue
            if not np.array_equal(colored[0], colored[1]):
                continue

            fill = int(colored[0].sum())
            if fill == 0:
                continue
            if not np.all(colored[0, :fill]) or np.any(colored[0, fill:]):
                continue
            bars.append({"x": x + 1, "y": y, "fill": fill})

    return bars


def find_scaled_bars(pixels: np.ndarray, color: np.ndarray) -> list[dict[str, int]]:
    """Find bars after OBS has rescaled the client and altered exact RGB values."""
    values = pixels.astype(np.int16)
    red, green, blue = values[:, :, 0], values[:, :, 1], values[:, :, 2]
    if np.array_equal(color, HEALTH_GREEN):
        mask = (green > 100) & (green > red + 45) & (green > blue + 45)
    elif np.array_equal(color, MANA_BLUE):
        mask = (blue > 100) & (blue > red + 45) & (blue > green + 45)
    else:
        return []

    count, _labels, stats, _centers = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    bars = []
    for x, y, width, height, area in stats[1:count]:
        if not (1 <= width <= INNER_WIDTH + 4 and 1 <= height <= 5):
            continue
        if area < width * height * 0.55:
            continue
        bars.append({"x": int(x), "y": int(y), "fill": int(width)})
    return bars


def find_bar_pairs(pixels: np.ndarray) -> list[tuple[dict[str, int], dict[str, int]]]:
    health_bars = find_bars(pixels, HEALTH_GREEN)
    mana_bars = find_bars(pixels, MANA_BLUE)
    exact = [
        (health, mana)
        for health in health_bars
        for mana in mana_bars
        if health["x"] == mana["x"] and mana["y"] - health["y"] == 5
    ]
    if exact:
        return exact

    health_bars = find_scaled_bars(pixels, HEALTH_GREEN)
    mana_bars = find_scaled_bars(pixels, MANA_BLUE)
    return [
        (health, mana)
        for health in health_bars
        for mana in mana_bars
        if abs(health["x"] - mana["x"]) <= 2 and 3 <= mana["y"] - health["y"] <= 7
    ]


def fill_percent(fill: int) -> float:
    # One source pixel can disappear in OBS's canvas scaling even on a full bar.
    return 100.0 if fill >= INNER_WIDTH - 1 else round(fill / INNER_WIDTH * 100, 1)


def read_status(image_path: Path) -> dict:
    image = Image.open(image_path).convert("RGB")
    pixels = np.asarray(image, dtype=np.uint8)
    pairs = find_bar_pairs(pixels)
    result = {"image": str(image_path.resolve())}
    if pairs:
        center_x = pixels.shape[1] / 2
        center_y = pixels.shape[0] / 2
        health, mana = min(
            pairs,
            key=lambda pair: abs(pair[0]["x"] + INNER_WIDTH / 2 - center_x)
            + abs(pair[0]["y"] - center_y),
        )
        result.update(
            {
                "health_percent": fill_percent(health["fill"]),
                "mana_percent": fill_percent(mana["fill"]),
                "health_fill_pixels": health["fill"],
                "mana_fill_pixels": mana["fill"],
                "bar_inner_width": INNER_WIDTH,
                "bar_position": {
                    "x": health["x"],
                    "health_y": health["y"],
                    "mana_y": mana["y"],
                },
                "note": "As barras mostram percentual; valores numericos exigem screenshot da interface completa.",
            }
        )
    numeric = read_numeric_hud(image)
    if numeric:
        result.update(numeric)
        result["note"] = "Valores numericos lidos da interface completa; barras usadas como verificacao."
    if not pairs and not numeric:
        raise RuntimeError("Nao foi possivel ler HP e mana da captura")
    return result


def read_status_fast(image_path: Path) -> dict:
    """Prefer the numeric HUD, with centered character bars as fallback."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    numeric = read_numeric_hud(image)
    if numeric:
        return {
            "image": str(image_path.resolve()),
            "health_percent": numeric["health_numeric_percent"],
            "mana_percent": numeric["mana_numeric_percent"],
            "health": numeric["health"],
            "mana": numeric["mana"],
            "mode": "numeric_hud",
        }
    width, height = image.size
    gameplay_center_x = round((width - 352) / 2)
    gameplay_center_y = min(302, height // 2)
    left = max(0, gameplay_center_x - 90)
    top = max(0, gameplay_center_y - 90)
    right = min(width, gameplay_center_x + 90)
    bottom = min(height, gameplay_center_y + 30)
    pixels = np.asarray(image.crop((left, top, right, bottom)), dtype=np.uint8)
    pairs = find_bar_pairs(pixels)
    if not pairs:
        wide_left = max(0, gameplay_center_x - 140)
        wide_right = min(width, gameplay_center_x + 140)
        wide_top = max(0, gameplay_center_y - 120)
        wide_bottom = min(height, gameplay_center_y + 50)
        wide_pixels = np.asarray(
            image.crop((wide_left, wide_top, wide_right, wide_bottom)),
            dtype=np.uint8,
        )
        pairs = find_bar_pairs(wide_pixels)
        if pairs:
            left, top = wide_left, wide_top
            pixels = wide_pixels
    if not pairs:
        raise RuntimeError("Nao foi possivel ler rapidamente as barras do personagem")
    center_x = pixels.shape[1] / 2
    center_y = pixels.shape[0] / 2
    health, mana = min(
        pairs,
        key=lambda pair: abs(pair[0]["x"] + INNER_WIDTH / 2 - center_x)
        + abs(pair[0]["y"] - center_y),
    )
    return {
        "image": str(image_path.resolve()),
        "health_percent": fill_percent(health["fill"]),
        "mana_percent": fill_percent(mana["fill"]),
        "health_fill_pixels": health["fill"],
        "mana_fill_pixels": mana["fill"],
        "bar_inner_width": INNER_WIDTH,
        "bar_position": {
            "x": left + health["x"],
            "health_y": top + health["y"],
            "mana_y": top + mana["y"],
        },
        "mode": "fast_character_bars",
    }


def ocr_fraction(image: Image.Image, box: tuple[int, int, int, int]) -> dict | None:
    try:
        import pytesseract
    except ImportError:
        return None

    crop = image.crop(box).getchannel("R")
    for threshold in (140, 120, 100):
        binary = crop.point(lambda value, limit=threshold: 255 if value > limit else 0)
        enlarged = binary.resize((binary.width * 8, binary.height * 8))
        text = pytesseract.image_to_string(
            enlarged,
            config="--psm 7 -c tessedit_char_whitelist=0123456789/()",
        )
        match = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if not match:
            continue
        current, maximum = map(int, match.groups())
        if maximum > 0 and current <= maximum:
            return {
                "current": current,
                "maximum": maximum,
                "ocr_text": text.strip(),
                "threshold": threshold,
            }
    return None


def read_numeric_hud(image: Image.Image) -> dict:
    width, height = image.size
    if width < 1000:
        return {}

    strip_height = max(28, round(height * 0.04))
    health = ocr_fraction(
        image,
        (round(width * 0.12), 0, round(width * 0.28), strip_height),
    )
    mana = ocr_fraction(
        image,
        (round(width * 0.44), 0, round(width * 0.68), strip_height),
    )
    if health is None or mana is None:
        return {}
    return {
        "health": health,
        "mana": mana,
        "health_numeric_percent": round(health["current"] / health["maximum"] * 100, 1),
        "mana_numeric_percent": round(mana["current"] / mana["maximum"] * 100, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", type=Path, help="Screenshot interno do Tibia")
    args = parser.parse_args()

    image_path = args.image
    if image_path is None:
        capture_dir = Path(__file__).resolve().parent / "internal_captures"
        files = list(capture_dir.glob("*.png"))
        if not files:
            raise RuntimeError("Nenhuma captura interna encontrada")
        image_path = max(files, key=lambda path: path.stat().st_mtime_ns)

    print(json.dumps(read_status(image_path), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
