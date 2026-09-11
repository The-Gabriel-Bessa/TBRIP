"""Approach one detected corpse step by step, then quick-loot it once."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autoloot.approach_plan import DIRECTIONS  # noqa: E402
from autoloot.detect_corpses import detect_corpses  # noqa: E402
from autoloot.loot_once import perform_autoloot  # noqa: E402
from autoloot.select_loot_tab import capture_to  # noqa: E402
from capture_internal import find_window, press_key  # noqa: E402


user32 = ctypes.windll.user32
VK_RETURN = 0x0D
KEY_TO_VK = {key: ord(key) for key in DIRECTIONS.values()}
KEY_TO_MOVE = {key: vector for vector, key in DIRECTIONS.items()}


def focus_game(hwnd: int) -> None:
    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.2)


def choose_nearest(detections: list[dict], expected_offset: list[int] | None = None) -> dict:
    if not detections:
        raise RuntimeError("O corpo nao foi encontrado novamente")
    if expected_offset is None:
        return min(
            detections,
            key=lambda corpse: max(abs(value) for value in corpse["tile_offset_from_player"]),
        )
    return min(
        detections,
        key=lambda corpse: sum(
            abs(corpse["tile_offset_from_player"][index] - expected_offset[index])
            for index in (0, 1)
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--creature", choices=("Amazon", "Valkyrie", "Witch"), required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--encounter-id", required=True)
    parser.add_argument("--initial-chat", choices=("on", "off"), default="on")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()

    autoloot_dir = Path(__file__).resolve().parent
    tibia_dir = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia"
    source_folder = tibia_dir / "screenshots"
    output_folder = autoloot_dir / "captures"
    ledger_path = autoloot_dir / "loot_attempts.jsonl"
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window("Tibia -")
    chat_off = args.initial_chat == "off"
    if not chat_off:
        focus_game(hwnd)
        press_key(VK_RETURN)
        chat_off = True

    movement_log = []
    current_screenshot = args.image.resolve()
    try:
        detection = detect_corpses(current_screenshot, {args.creature: args.count})
        corpse = choose_nearest(detection["detections"])
        offset = corpse["tile_offset_from_player"]
        keys = corpse["approach"]["keys"][: args.max_steps]

        for key in keys:
            move_x, move_y = KEY_TO_MOVE[key]
            expected_offset = [offset[0] - move_x, offset[1] - move_y]
            previous_distance = max(abs(offset[0]), abs(offset[1]))

            focus_game(hwnd)
            press_key(KEY_TO_VK[key])
            time.sleep(0.6)
            current_screenshot = capture_to(hwnd, source_folder, output_folder)
            detection = detect_corpses(current_screenshot, {args.creature: args.count})
            corpse = choose_nearest(detection["detections"], expected_offset)
            observed_offset = corpse["tile_offset_from_player"]
            observed_distance = max(abs(observed_offset[0]), abs(observed_offset[1]))
            step = {
                "key": key,
                "before": offset,
                "expected": expected_offset,
                "observed": observed_offset,
                "score": corpse["score"],
                "screenshot": str(current_screenshot),
            }
            movement_log.append(step)
            if observed_distance >= previous_distance:
                raise RuntimeError(f"Movimento nao aproximou do corpo: {step}")
            offset = observed_offset
            if max(abs(offset[0]), abs(offset[1])) <= 1:
                break

        if max(abs(offset[0]), abs(offset[1])) > 1:
            raise RuntimeError(f"Corpo ainda nao esta adjacente: offset={offset}")

        loot_result = perform_autoloot(
            hwnd=hwnd,
            encounter_id=args.encounter_id,
            current_screenshot=current_screenshot,
            source_folder=source_folder,
            output_folder=output_folder,
            ledger_path=ledger_path,
        )
        result = {
            "status": "completed",
            "window": title,
            "creature": args.creature,
            "movement": movement_log,
            "final_offset": offset,
            "loot": loot_result,
        }
    finally:
        if chat_off:
            focus_game(hwnd)
            press_key(VK_RETURN)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
