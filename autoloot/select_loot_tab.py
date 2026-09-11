"""Locate and select Tibia's Loot chat tab, then OCR its visible log."""

from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import Output


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from attack_once import POINT, screenshot_to_screen  # noqa: E402
from capture_internal import find_window, trigger_screenshot_with_retry  # noqa: E402
from runtime.capture_store import store_generated_screenshot  # noqa: E402


user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def locate_loot_tab(image_path: Path) -> dict:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    box = (0, round(height * 0.84), round(width * 0.32), round(height * 0.92))
    roi = image.crop(box)
    scale = 4
    enlarged = roi.resize((roi.width * scale, roi.height * scale))
    data = pytesseract.image_to_data(enlarged, config="--psm 6", output_type=Output.DICT)

    candidates = []
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        if text.casefold() != "loot":
            continue
        confidence = float(data["conf"][index])
        x = box[0] + data["left"][index] // scale
        y = box[1] + data["top"][index] // scale
        token_width = max(1, data["width"][index] // scale)
        token_height = max(1, data["height"][index] // scale)
        candidates.append(
            {
                "text": text,
                "confidence": round(confidence, 1),
                "box": [x, y, token_width, token_height],
                "screenshot_click": [x + token_width // 2, y + token_height // 2],
            }
        )

    if not candidates:
        raise RuntimeError("A aba Loot nao foi encontrada por OCR")
    return max(candidates, key=lambda item: item["confidence"])


def read_visible_log(image_path: Path) -> str:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    box = (0, round(height * 0.90), round(width * 0.72), round(height * 0.975))
    roi = image.crop(box)
    scale = 4
    enlarged = roi.resize((roi.width * scale, roi.height * scale))
    return pytesseract.image_to_string(enlarged, config="--psm 6").strip()


def click_tab(hwnd: int, image_path: Path, tab: dict) -> list[int]:
    screen_point = screenshot_to_screen(hwnd, image_path, tab["screenshot_click"])
    previous_cursor = POINT()
    user32.GetCursorPos(ctypes.byref(previous_cursor))
    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.25)
    user32.SetCursorPos(screen_point.x, screen_point.y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)
    user32.SetCursorPos(previous_cursor.x, previous_cursor.y)
    return [screen_point.x, screen_point.y]


def capture_to(hwnd: int, source_folder: Path, output_folder: Path) -> Path:
    source = trigger_screenshot_with_retry(hwnd, source_folder)
    return store_generated_screenshot(source, output_folder)


def main() -> int:
    tibia_folder = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia"
    source_folder = tibia_folder / "screenshots"
    output_folder = Path(__file__).resolve().parent / "captures"
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window("Tibia -")
    before = capture_to(hwnd, source_folder, output_folder)
    tab = locate_loot_tab(before)
    screen_click = click_tab(hwnd, before, tab)
    after = capture_to(hwnd, source_folder, output_folder)
    visible_log = read_visible_log(after)

    result = {
        "action": "loot_tab_clicked",
        "window": title,
        "tab": tab,
        "screen_click": screen_click,
        "before": str(before),
        "after": str(after),
        "visible_log_ocr": visible_log,
        "verified_by_log_text": any(
            marker in visible_log.casefold()
            for marker in ("loot of", "you looted", "nothing", "gold coin")
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
