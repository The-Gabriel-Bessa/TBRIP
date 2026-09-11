"""Perform one guarded quick-loot attempt and persist its result."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from capture_internal import find_window, press_key  # noqa: E402
from autoloot.loot_log import parse_new_entries, terminal_entries  # noqa: E402
from autoloot.select_loot_tab import (  # noqa: E402
    capture_to,
    click_tab,
    locate_loot_tab,
    read_visible_log,
)

if TYPE_CHECKING:
    from runtime.frame_source import CaptureSession


user32 = ctypes.windll.user32
VK_MENU = 0x12
VK_Q = 0x51
KEYEVENTF_KEYUP = 0x0002


def attempted_encounters(ledger_path: Path) -> set[str]:
    if not ledger_path.exists():
        return set()
    attempts = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        encounter_id = record.get("encounter_id")
        if encounter_id:
            attempts.add(encounter_id)
    return attempts


def append_ledger(ledger_path: Path, record: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(record, ensure_ascii=False) + "\n")


def press_quick_loot(hwnd: int) -> None:
    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.2)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    try:
        press_key(VK_Q)
    finally:
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def perform_autoloot(
    hwnd: int,
    encounter_id: str,
    current_screenshot: Path,
    source_folder: Path,
    output_folder: Path,
    ledger_path: Path,
    capture_session: CaptureSession | None = None,
) -> dict:
    if encounter_id in attempted_encounters(ledger_path):
        return {
            "status": "skipped_already_attempted",
            "encounter_id": encounter_id,
            "attempted": False,
        }

    tab = locate_loot_tab(current_screenshot)
    tab_screen_click = click_tab(hwnd, current_screenshot, tab)
    baseline_screenshot = capture_to(hwnd, source_folder, output_folder, capture_session)
    baseline_log = read_visible_log(baseline_screenshot)

    press_quick_loot(hwnd)
    attempted_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    time.sleep(1.0)

    result_tab_screen_click = click_tab(hwnd, baseline_screenshot, tab)
    result_screenshot = capture_to(hwnd, source_folder, output_folder, capture_session)
    result_log = read_visible_log(result_screenshot)
    new_entries = parse_new_entries(baseline_log, result_log)
    confirmed_entries = terminal_entries(new_entries)
    wanted_items = [
        item
        for entry in confirmed_entries
        if entry["type"] == "loot_of" and entry.get("wanted_creature")
        for item in entry.get("wanted_items", [])
    ]
    if wanted_items:
        status = "confirmed_wanted_items"
    elif confirmed_entries:
        status = "confirmed_no_wanted_items"
    else:
        status = "attempted_without_loot_log_confirmation"

    record = {
        "encounter_id": encounter_id,
        "attempted_at": attempted_at,
        "status": status,
        "attempted": True,
        "hotkey": "Alt+Q",
        "tab_screenshot_click": tab["screenshot_click"],
        "tab_screen_click": tab_screen_click,
        "result_tab_screen_click": result_tab_screen_click,
        "baseline_screenshot": str(baseline_screenshot),
        "result_screenshot": str(result_screenshot),
        "baseline_log_ocr": baseline_log,
        "result_log_ocr": result_log,
        "new_entries": new_entries,
        "confirmed_entries": confirmed_entries,
        "wanted_items": wanted_items,
    }
    append_ledger(ledger_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--encounter-id", default=f"manual-{time.time_ns()}")
    args = parser.parse_args()

    autoloot_dir = Path(__file__).resolve().parent
    tibia_dir = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia"
    source_folder = tibia_dir / "screenshots"
    output_folder = autoloot_dir / "captures"
    ledger_path = autoloot_dir / "loot_attempts.jsonl"
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, _title = find_window("Tibia -")
    current_screenshot = capture_to(hwnd, source_folder, output_folder)
    result = perform_autoloot(
        hwnd=hwnd,
        encounter_id=args.encounter_id,
        current_screenshot=current_screenshot,
        source_folder=source_folder,
        output_folder=output_folder,
        ledger_path=ledger_path,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
