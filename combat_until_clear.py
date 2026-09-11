"""Attack confirmed Battle List targets until combat ends."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from attack_once import POINT, screenshot_to_screen
from autoloot.detect_corpses import detect_corpses

# Criaturas que dropam itens desejados (Witch Broom, Girlish Hair Decoration, Protective Charm)
LOOTABLE_CREATURES = {"Amazon", "Witch", "Valkyrie"}
from autoloot.mapped_loot import perform_mapped_autoloot
from autoloot.read_world_targets import read_world_targets
from combat_feedback import read_combat_feedback
from capture_internal import find_window, focus_window, press_key
from movement.pathfinding import attack_range_approach
from movement.safe_walk import execute_sequence
from movement.world_model import analyze_world, localize_in_reference
from read_battle_list import read_battle_list
from read_status_bars import read_status_fast
from runtime.chat_state import ensure_chat_off
from runtime.frame_source import CAPTURE_MODES, VCAM_DEVICE, CaptureSession


user32 = ctypes.windll.user32
VK_O = 0x4F
VK_P = 0x50
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def emit(event: str, **values) -> None:
    print(
        json.dumps({"time": time.strftime("%H:%M:%S"), "event": event, **values}, ensure_ascii=True),
        flush=True,
    )


def focus_game(hwnd: int) -> None:
    focus_window(hwnd)
    time.sleep(0.2)


def click_target_and_fire(hwnd: int, image: Path, target: dict) -> list[int]:
    screen_point = screenshot_to_screen(hwnd, image, target["screenshot_click"])
    previous_cursor = POINT()
    user32.GetCursorPos(ctypes.byref(previous_cursor))
    focus_game(hwnd)
    try:
        user32.SetCursorPos(screen_point.x, screen_point.y)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        try:
            time.sleep(0.05)
        finally:
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.12)
        press_key(VK_P, hwnd)
    finally:
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        user32.SetCursorPos(previous_cursor.x, previous_cursor.y)
    return [screen_point.x, screen_point.y]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--silence", type=float, default=2.0)
    parser.add_argument("--heal-below", type=float, default=70.0)
    parser.add_argument("--attack-interval", type=float, default=1.2)
    parser.add_argument("--capture-source", choices=CAPTURE_MODES, default="auto")
    parser.add_argument("--obs-device", default=VCAM_DEVICE)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--initial-enemy", action="append", default=[])
    parser.add_argument(
        "--autoloot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Aproxima pelos tiles verdes e executa Alt+Q; use --no-autoloot para desativar",
    )
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error("--max-seconds deve ser um numero positivo")
    if not math.isfinite(args.attack_interval) or args.attack_interval <= 0:
        parser.error("--attack-interval deve ser um numero positivo")
    if not math.isfinite(args.heal_below) or not 0 <= args.heal_below <= 100:
        parser.error("--heal-below deve estar entre 0 e 100")

    project = Path(__file__).resolve().parent
    source_folder = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia" / "screenshots"
    output_folder = project / "runtime" / "captures"
    reference_path = project / "movement" / "amazon_camp_cave_reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window("Tibia -")
    started = time.monotonic()
    attacks = 0
    heals = 0
    last_heal = 0.0
    last_attack = 0.0
    reason = "max_duration"
    unmatched_scans = 0
    chat_state: dict | None = None
    encounter_id = f"combat-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}"
    autoloot_result: dict | None = None
    corpse_detection: dict | None = None
    maximum_counts: Counter = Counter(args.initial_enemy)
    unresolved_out_of_range = 0

    capture_session = CaptureSession.for_window(
        hwnd,
        mode=args.capture_source,
        ffmpeg_path=args.ffmpeg,
        device=args.obs_device,
    )
    readers: ThreadPoolExecutor | None = None
    capture_mode = "stopped"
    capture_stats: dict = {}

    def analyze_frame(image: Path) -> dict:
        assert readers is not None
        battle_future = readers.submit(read_battle_list, image)
        status_future = readers.submit(read_status_fast, image)
        feedback_future = readers.submit(read_combat_feedback, image)
        battle = battle_future.result()
        try:
            status = status_future.result()
        except Exception as exc:
            emit("status_read_failed", error=str(exc))
            status = {
                "health_percent": 100,
                "mana_percent": 100,
                "mode": "fallback_safe",
            }
        feedback = feedback_future.result()
        result = {"battle": battle, "status": status, "feedback": feedback}
        if feedback["destination_out_of_range"]:
            targets_future = readers.submit(read_world_targets, image)
            map_future = readers.submit(analyze_world, image, "Rafaelkrosa", False)
            result["world_targets"] = targets_future.result()
            result["map_analysis"] = map_future.result()
        else:
            result["world_targets"] = {"targets": []}
            result["map_analysis"] = None
        return result

    try:
        capture_session.start()
        readers = ThreadPoolExecutor(max_workers=5, thread_name_prefix="combat-reader")
        capture_mode = capture_session.active_mode
        emit("combat_loop_started", window=title, capture=capture_session.stats())
        while time.monotonic() - started < args.max_seconds:
            saved, scan = capture_session.capture_and_analyze(
                hwnd,
                source_folder,
                output_folder,
                analyze_frame,
            )
            if capture_session.active_mode != capture_mode:
                capture_mode = capture_session.active_mode
                emit("capture_source_changed", capture=capture_session.stats())
            battle = scan["battle"]
            status = scan["status"]
            feedback = scan["feedback"]
            world_targets = scan["world_targets"]
            map_analysis = scan["map_analysis"]
            if chat_state is None:
                chat_state = ensure_chat_off(
                    hwnd,
                    saved,
                    capture_session,
                    source_folder,
                    output_folder,
                )
                emit("chat_mode_checked", **chat_state)
                if chat_state.get("changed"):
                    continue
            hp_percent = status["health_percent"]
            enemies = battle["matched_enemies"]
            current_counts = Counter(enemy["name"] for enemy in enemies)
            for creature, count in current_counts.items():
                maximum_counts[creature] = max(maximum_counts[creature], count)
            emit(
                "scan",
                hp=hp_percent,
                mana=status["mana_percent"],
                entries=battle["visible_entries"],
                enemies=[enemy["name"] for enemy in enemies],
            )

            if hp_percent < args.heal_below:
                if time.monotonic() - last_heal >= 1.2:
                    focus_game(hwnd)
                    press_key(VK_O, hwnd)
                    heals += 1
                    last_heal = time.monotonic()
                    emit("healed", key="O", hp_before=hp_percent)
                time.sleep(0.1)
                continue

            if battle["empty"]:
                reason = "battle_list_empty"
                expected_corpses = {
                    creature: maximum_counts[creature]
                    for creature in maximum_counts
                    if creature in LOOTABLE_CREATURES
                    and maximum_counts[creature] > 0
                }
                if expected_corpses:
                    try:
                        corpse_detection = detect_corpses(saved, expected_corpses)
                        emit(
                            "corpses_detected",
                            expected=expected_corpses,
                            found=len(corpse_detection["detections"]),
                            offsets=[
                                corpse["tile_offset_from_player"]
                                for corpse in corpse_detection["detections"]
                            ],
                        )
                    except Exception as exc:
                        corpse_detection = {
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                        emit("corpse_detection_failed", **corpse_detection)
                if args.autoloot and (attacks > 0 or expected_corpses):
                    emit("autoloot_started", encounter_id=encounter_id, hotkey="Alt+Q")
                    try:
                        autoloot_result = perform_mapped_autoloot(
                            encounter_id=encounter_id,
                            current_screenshot=saved,
                            corpse_detection=corpse_detection,
                            reference_path=reference_path,
                            capture_session=capture_session,
                            heal_below=args.heal_below,
                        )
                        emit(
                            "autoloot_finished",
                            encounter_id=encounter_id,
                            status=autoloot_result["status"],
                            attempted=autoloot_result.get("attempted", 0),
                        )
                    except Exception as exc:
                        autoloot_result = {
                            "status": "error",
                            "encounter_id": encounter_id,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                        emit("autoloot_failed", **autoloot_result)
                elif attacks > 0:
                    autoloot_result = {
                        "status": "pending_corpse_approach",
                        "encounter_id": encounter_id,
                        "attempted": False,
                        "corpse_detection": corpse_detection,
                    }
                    emit("autoloot_deferred", **autoloot_result)
                break
            if not enemies:
                unmatched_scans += 1
                if unmatched_scans >= 2:
                    reason = "entries_not_whitelisted"
                    break
                time.sleep(0.4)
                continue

            unmatched_scans = 0
            target = enemies[0]
            if feedback["destination_out_of_range"]:
                visible_targets = [
                    item for item in world_targets["targets"] if item["name"] == target["name"]
                ]
                visible_targets.sort(
                    key=lambda item: (
                        item.get("name_color") != "red",
                        max(abs(value) for value in item["tile_offset_from_player"]),
                    )
                )
                localization = localize_in_reference(map_analysis, reference)
                if visible_targets and localization["localized"]:
                    chased_target = visible_targets[0]
                    try:
                        chase = attack_range_approach(
                            reference,
                            tuple(localization["coordinate"]),
                            chased_target["tile_offset_from_player"],
                            attack_range=1,
                        )
                        chase_keys = chase["keys"][:2]
                        if not chase_keys:
                            unresolved_out_of_range = 0
                            emit("target_already_in_range", target=target["name"])
                            until_attack = args.attack_interval - (time.monotonic() - last_attack)
                            if until_attack > 0:
                                time.sleep(min(0.1, until_attack))
                                continue
                            point = click_target_and_fire(hwnd, saved, target)
                            attacks += 1
                            last_attack = time.monotonic()
                            emit("attacked", target=target["name"], key="P", screen_click=point)
                            continue
                        chase_state = {
                            "frame_id": saved.stem,
                            "image": str(saved.resolve()),
                            "position": localization["coordinate"],
                            "localized": True,
                            "agreement": localization["best"]["agreement"],
                            "matching_tiles": localization["best"]["matching_tiles"],
                            "battle_empty": battle["empty"],
                            "enemies": [enemy["name"] for enemy in enemies],
                            "health_percent": status["health_percent"],
                            "mana_percent": status["mana_percent"],
                        }
                        movement, exit_code = execute_sequence(
                            chase_keys,
                            tuple(localization["coordinate"]),
                            reference_path,
                            allow_blocked=False,
                            verify_every=1,
                            initial_state=chase_state,
                            stop_on_enemies=False,
                            capture_session=capture_session,
                            heal_below=args.heal_below,
                        )
                        emit(
                            "target_chase",
                            target=target["name"],
                            observed_offset=chased_target["tile_offset_from_player"],
                            planned=chase_keys,
                            goal=chase["goal"],
                            completed=exit_code == 0,
                            final_position=movement.get("final_position"),
                        )
                        if exit_code != 0:
                            reason = "target_chase_failed"
                            break
                        unresolved_out_of_range = 0
                        reference = json.loads(reference_path.read_text(encoding="utf-8"))
                        continue
                    except Exception as exc:
                        emit("target_chase_failed", error=f"{type(exc).__name__}: {exc}")

                unresolved_out_of_range += 1
                emit(
                    "out_of_range_unresolved",
                    target=target["name"],
                    visible_targets=len(visible_targets),
                    attempts=unresolved_out_of_range,
                )
                if unresolved_out_of_range >= 3:
                    reason = "target_out_of_range_unresolved"
                    break
            else:
                unresolved_out_of_range = 0
            until_attack = args.attack_interval - (time.monotonic() - last_attack)
            if until_attack > 0:
                time.sleep(min(0.1, until_attack))
                continue
            point = click_target_and_fire(hwnd, saved, target)
            attacks += 1
            last_attack = time.monotonic()
            emit("attacked", target=target["name"], key="P", screen_click=point)
    finally:
        if readers is not None:
            readers.shutdown(wait=True, cancel_futures=True)
        capture_stats = capture_session.stats()
        capture_session.stop()

    if autoloot_result is not None and autoloot_result.get("status") in {
        "error",
        "partial",
        "aborted_unlocalized",
        "no_corpses_detected",
    }:
        reason = "autoloot_failed"

    emit(
        "combat_loop_stopped",
        reason=reason,
        attacks=attacks,
        heals=heals,
        chat=chat_state,
        autoloot=autoloot_result,
        corpse_detection=corpse_detection,
        capture=capture_stats,
    )
    return 0 if reason == "battle_list_empty" else 2


if __name__ == "__main__":
    raise SystemExit(main())
