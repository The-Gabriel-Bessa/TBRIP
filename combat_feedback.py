"""Read transient combat feedback rendered over the gameplay viewport."""

from __future__ import annotations

import re
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps


def is_destination_out_of_range(text: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", text.casefold())
    return "destinationisoutofrange" in normalized


def read_combat_feedback(image_path: Path) -> dict:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, _height = image.size
    center_x = round((width - 352) / 2)
    crop = image.crop((max(0, center_x - 136), 515, min(width, center_x + 184), 548))
    grayscale = ImageOps.grayscale(crop)
    binary = grayscale.point(lambda value: 255 if value > 180 else 0)
    enlarged = binary.resize((binary.width * 4, binary.height * 4))
    text = pytesseract.image_to_string(enlarged, config="--psm 7").strip()
    return {
        "image": str(image_path.resolve()),
        "text": text,
        "destination_out_of_range": is_destination_out_of_range(text),
    }
