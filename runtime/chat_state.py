"""Read and guard Tibia's Chat On/Off mode before keyboard actions."""

from __future__ import annotations

import ctypes
import re
import time
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from capture_internal import press_key
from runtime.frame_source import CaptureSession


user32 = ctypes.windll.user32
VK_RETURN = 0x0D


def classify_chat_texts(texts: list[str]) -> str:
    votes = []
    for text in texts:
        normalized = re.sub(r"[^a-z]", "", text.casefold())
        if not normalized.startswith(("chat", "chet")):
            continue
        if normalized.endswith(("off", "of")):
            votes.append("off")
        elif normalized.endswith(("on", "one", "ont")):
            votes.append("on")
    if votes and all(vote == votes[0] for vote in votes):
        return votes[0]
    return "unknown"


def read_chat_mode(image_path: Path) -> dict:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    box = (image.width - 452, image.height - 29, image.width - 352, image.height)
    grayscale = ImageOps.grayscale(image.crop(box))
    texts = []
    for threshold in (120, 140, 160):
        binary = grayscale.point(lambda value, limit=threshold: 255 if value > limit else 0)
        enlarged = binary.resize((binary.width * 8, binary.height * 8))
        text = pytesseract.image_to_string(
            enlarged,
            config="--psm 7 -c tessedit_char_whitelist=ChatOnFfchatonf",
        ).strip()
        if text:
            texts.append(text)
    return {
        "mode": classify_chat_texts(texts),
        "texts": texts,
        "region": list(box),
        "image": str(image_path.resolve()),
    }


def ensure_chat_off(
    hwnd: int,
    image_path: Path,
    capture_session: CaptureSession,
    source_folder: Path,
    output_folder: Path,
) -> dict:
    if capture_session.chat_off_confirmed:
        return {"mode": "off", "changed": False, "source": "capture_session"}

    before = read_chat_mode(image_path)
    if before["mode"] == "unknown":
        raise RuntimeError(f"Nao foi possivel confirmar Chat Off: {before['texts']}")
    if before["mode"] == "off":
        capture_session.chat_off_confirmed = True
        return {"mode": "off", "changed": False, "before": before}

    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.1)
    press_key(VK_RETURN)
    time.sleep(0.2)
    verification_image = capture_session.capture(hwnd, source_folder, output_folder)
    after = read_chat_mode(verification_image)
    if after["mode"] != "off":
        raise RuntimeError(f"Chat continuou em modo {after['mode']}: {after['texts']}")
    capture_session.chat_off_confirmed = True
    return {"mode": "off", "changed": True, "before": before, "after": after}
