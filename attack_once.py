"""Capture the current Battle List and attack one confirmed target."""

from __future__ import annotations

import ctypes
import json
import shutil
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

from capture_internal import find_window, press_key, trigger_screenshot
from read_battle_list import read_battle_list


user32 = ctypes.windll.user32
VK_P = 0x50
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def screenshot_to_screen(hwnd: int, image_path: Path, point: list[int]) -> POINT:
    client = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise ctypes.WinError()
    client_width = client.right - client.left
    client_height = client.bottom - client.top
    with Image.open(image_path) as image:
        client_x = round(point[0] * client_width / image.width)
        client_y = round(point[1] * client_height / image.height)
    screen_point = POINT(client_x, client_y)
    if not user32.ClientToScreen(hwnd, ctypes.byref(screen_point)):
        raise ctypes.WinError()
    return screen_point


def main() -> int:
    project = Path(__file__).resolve().parent
    source_folder = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia" / "screenshots"
    output_folder = project / "internal_captures"
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window("Tibia -")
    source = trigger_screenshot(hwnd, source_folder)
    saved = output_folder / source.name
    shutil.copy2(source, saved)
    battle = read_battle_list(saved)
    if not battle["matched_enemies"]:
        print(
            json.dumps(
                {
                    "action": "none",
                    "reason": "Nenhum alvo confirmado na Battle List",
                    "visible_entries": battle["visible_entries"],
                    "screenshot": str(saved),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    target = battle["matched_enemies"][0]
    screen_point = screenshot_to_screen(hwnd, saved, target["screenshot_click"])
    previous_cursor = POINT()
    user32.GetCursorPos(ctypes.byref(previous_cursor))

    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.25)
    user32.SetCursorPos(screen_point.x, screen_point.y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.15)
    press_key(VK_P)
    time.sleep(0.1)
    user32.SetCursorPos(previous_cursor.x, previous_cursor.y)

    print(
        json.dumps(
            {
                "action": "clicked_and_pressed_p",
                "window": title,
                "target": target,
                "screen_click": [screen_point.x, screen_point.y],
                "screenshot": str(saved),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
