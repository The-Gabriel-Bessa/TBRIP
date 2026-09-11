"""Locate Tibia's minimap and apply a repeatable five-step zoom-in."""

from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from attack_once import POINT, screenshot_to_screen  # noqa: E402
from capture_internal import find_window, press_key, trigger_screenshot  # noqa: E402


user32 = ctypes.windll.user32
VK_RETURN = 0x0D
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


def capture_to(hwnd: int, source_folder: Path, output_folder: Path) -> Path:
    source = trigger_screenshot(hwnd, source_folder)
    destination = output_folder / source.name
    shutil.copy2(source, destination)
    return destination


def locate_minimap(image_path: Path) -> dict:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    if width < 1000:
        raise RuntimeError("A captura nao inclui a interface completa")

    # The right sidebar uses fixed-size controls, so right-edge offsets remain
    # stable when the screenshot changes between windowed and maximized sizes.
    box = (width - 168, 4, width - 65, min(117, height))
    crop = np.asarray(image.crop(box), dtype=np.uint8)
    crop_height, crop_width, _channels = crop.shape
    aspect_ratio = crop_width / crop_height
    channel_range = crop.max(axis=2).astype(np.int16) - crop.min(axis=2).astype(np.int16)
    colorful_percent = float((channel_range >= 30).mean() * 100)
    luminance_std = float(crop.mean(axis=2).std())
    valid = 0.8 <= aspect_ratio <= 1.2 and colorful_percent >= 1.0 and luminance_std >= 10.0
    if not valid:
        raise RuntimeError(
            "A regiao esperada do minimapa falhou na validacao: "
            f"aspect={aspect_ratio:.3f}, colorful={colorful_percent:.2f}, std={luminance_std:.2f}"
        )

    return {
        "box": list(box),
        "center": [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2],
        "size": [crop_width, crop_height],
        "aspect_ratio": round(aspect_ratio, 3),
        "colorful_percent": round(colorful_percent, 2),
        "luminance_std": round(luminance_std, 2),
        "validated": True,
    }


def scroll_up(hwnd: int, image_path: Path, center: list[int], steps: int) -> list[int]:
    screen_point = screenshot_to_screen(hwnd, image_path, center)
    previous_cursor = POINT()
    user32.GetCursorPos(ctypes.byref(previous_cursor))
    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.25)
    user32.SetCursorPos(screen_point.x, screen_point.y)
    for _ in range(steps):
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_DELTA, 0)
        time.sleep(0.15)
    user32.SetCursorPos(previous_cursor.x, previous_cursor.y)
    return [screen_point.x, screen_point.y]


def crop_minimap(image_path: Path, minimap: dict, output_path: Path) -> None:
    with Image.open(image_path) as image:
        image.crop(tuple(minimap["box"])).save(output_path)


def minimap_difference(
    before_path: Path,
    after_path: Path,
    before_box: list[int],
    after_box: list[int],
) -> dict:
    with Image.open(before_path) as before_image:
        before_crop = before_image.convert("RGB").crop(tuple(before_box))
    with Image.open(after_path) as after_image:
        after_crop = after_image.convert("RGB").crop(tuple(after_box)).resize(before_crop.size)
    before = np.asarray(before_crop, dtype=np.int16)
    after = np.asarray(after_crop, dtype=np.int16)
    difference = np.abs(after - before)
    changed_pixels = np.any(difference >= 10, axis=2)
    return {
        "mean_absolute_difference": round(float(difference.mean()), 3),
        "changed_pixels_percent": round(float(changed_pixels.mean() * 100), 3),
        "visually_changed": bool(changed_pixels.mean() >= 0.02),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=5)
    args = parser.parse_args()
    steps = max(0, min(args.steps, 10))

    movement_dir = Path(__file__).resolve().parent
    output_folder = movement_dir / "captures"
    tibia_dir = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia"
    source_folder = tibia_dir / "screenshots"
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window("Tibia -")
    chat_off_confirmed = False
    try:
        before = capture_to(hwnd, source_folder, output_folder)
        chat_off_confirmed = True
        minimap_before = locate_minimap(before)
        screen_point = scroll_up(hwnd, before, minimap_before["center"], steps)
        time.sleep(0.5)
        after = capture_to(hwnd, source_folder, output_folder)
        minimap_after = locate_minimap(after)

        before_crop = output_folder / f"{before.stem}_minimap.png"
        after_crop = output_folder / f"{after.stem}_minimap.png"
        crop_minimap(before, minimap_before, before_crop)
        crop_minimap(after, minimap_after, after_crop)
        difference = minimap_difference(
            before,
            after,
            minimap_before["box"],
            minimap_after["box"],
        )
    finally:
        if chat_off_confirmed:
            user32.SwitchToThisWindow(hwnd, True)
            time.sleep(0.2)
            press_key(VK_RETURN)

    result = {
        "action": "minimap_zoom_in",
        "window": title,
        "scroll_steps": steps,
        "minimap": minimap_before,
        "minimap_after": minimap_after,
        "screen_point": screen_point,
        "before": str(before),
        "after": str(after),
        "before_crop": str(before_crop),
        "after_crop": str(after_crop),
        "difference": difference,
        "final_chat": "on",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
