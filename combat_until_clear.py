"""Attack confirmed Battle List targets until combat ends."""

from __future__ import annotations

import argparse
import ctypes
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

import comtypes
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

from attack_once import POINT, screenshot_to_screen
from fast_attack import FastAttackGuard
from autoloot.detect_corpses import detect_corpses

# Criaturas que dropam itens desejados (Witch Broom, Girlish Hair Decoration, Protective Charm)
LOOTABLE_CREATURES = {"Amazon", "Witch", "Valkyrie"}
from autoloot.mapped_loot import perform_mapped_autoloot
from autoloot.read_world_targets import read_world_targets
from combat_feedback import read_combat_feedback
from capture_internal import find_window, press_key, trigger_screenshot_with_retry
from movement.pathfinding import attack_range_approach
from movement.safe_walk import execute_sequence
from movement.world_model import analyze_world, localize_in_reference
from read_battle_list import read_battle_list
from read_status_bars import read_status_fast
from runtime.capture_store import store_generated_screenshot


user32 = ctypes.windll.user32
VK_O = 0x4F
VK_P = 0x50
VK_RETURN = 0x0D
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def emit(event: str, **values) -> None:
    print(
        json.dumps({"time": time.strftime("%H:%M:%S"), "event": event, **values}, ensure_ascii=True),
        flush=True,
    )


def window_process_id(hwnd: int) -> int:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return process_id.value


class AudioTracker(threading.Thread):
    def __init__(self, process_id: int, marker: Path, threshold: float = 0.05):
        super().__init__(daemon=True)
        self.process_id = process_id
        self.marker = marker
        self.threshold = threshold
        self.last_sound = 0.0
        self.ever_heard_sound = False
        self.peak_max = 0.0
        self.error: str | None = None
        self.stop_event = threading.Event()

    def run(self) -> None:
        comtypes.CoInitialize()
        try:
            session = next(
                item
                for item in AudioUtilities.GetAllSessions()
                if item.ProcessId == self.process_id
            )
            meter = session._ctl.QueryInterface(IAudioMeterInformation)
            marker_was_present = False
            ignored_until = 0.0
            while not self.stop_event.is_set():
                now = time.monotonic()
                marker_present = self.marker.exists()
                if marker_was_present and not marker_present:
                    ignored_until = now + 0.75
                marker_was_present = marker_present
                peak = float(meter.GetPeakValue())
                self.peak_max = max(self.peak_max, peak)
                if marker_present or now < ignored_until:
                    self.last_sound = now
                elif peak >= self.threshold:
                    self.last_sound = now
                    self.ever_heard_sound = True
                time.sleep(0.01)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            comtypes.CoUninitialize()

    def stop(self) -> None:
        self.stop_event.set()

    def silent_for(self) -> float:
        return time.monotonic() - self.last_sound


def focus_game(hwnd: int) -> None:
    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.2)


def click_target_and_fire(hwnd: int, image: Path, target: dict) -> list[int]:
    screen_point = screenshot_to_screen(hwnd, image, target["screenshot_click"])
    previous_cursor = POINT()
    user32.GetCursorPos(ctypes.byref(previous_cursor))
    focus_game(hwnd)
    user32.SetCursorPos(screen_point.x, screen_point.y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.12)
    press_key(VK_P)
    user32.SetCursorPos(previous_cursor.x, previous_cursor.y)
    return [screen_point.x, screen_point.y]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--silence", type=float, default=2.0)
    parser.add_argument("--heal-below", type=float, default=70.0)
    parser.add_argument(
        "--autoloot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Aproxima pelos tiles verdes e executa Alt+Q; use --no-autoloot para desativar",
    )
    args = parser.parse_args()

    project = Path(__file__).resolve().parent
    source_folder = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia" / "screenshots"
    output_folder = project / "runtime" / "captures"
    reference_path = project / "movement" / "amazon_camp_cave_reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    marker = project / ".capture_in_progress"
    output_folder.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window("Tibia -")
    process_id = window_process_id(hwnd)
    audio = AudioTracker(process_id, marker)
    audio.start()
    # Insta-ataque: qualquer som do Tibia -> clica no 1o slot da battle list + P
    # em ~50-100ms, sem esperar o scan lento (screenshot + OCR = 2-4s).
    fast_guard = FastAttackGuard(
        hwnd,
        audio,
        marker=marker,
        trigger_window=0.35,
        cooldown=0.9,
        on_attack=lambda result: emit("fast_attack", reason="audio_trigger", **result),
    )
    fast_guard.start()
    started = time.monotonic()
    attacks = 0
    heals = 0
    last_heal = 0.0
    reason = "max_duration"
    unmatched_scans = 0
    chat_off_confirmed = False
    encounter_id = f"combat-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}"
    autoloot_result: dict | None = None
    corpse_detection: dict | None = None
    previous_counts: Counter = Counter()
    maximum_counts: Counter = Counter()
    detected_deaths: Counter = Counter()
    unresolved_out_of_range = 0

    emit("combat_loop_started", pid=process_id, window=title)
    readers = ThreadPoolExecutor(max_workers=5, thread_name_prefix="combat-reader")
    try:
        while time.monotonic() - started < args.max_seconds:
            source = trigger_screenshot_with_retry(hwnd, source_folder)
            chat_off_confirmed = True
            saved = store_generated_screenshot(source, output_folder)
            battle_future = readers.submit(read_battle_list, saved)
            status_future = readers.submit(read_status_fast, saved)
            feedback_future = readers.submit(read_combat_feedback, saved)
            targets_future = readers.submit(read_world_targets, saved)
            map_future = readers.submit(analyze_world, saved, "Rafaelkrosa", False)
            battle = battle_future.result()
            status = status_future.result()
            feedback = feedback_future.result()
            world_targets = targets_future.result()
            map_analysis = map_future.result()
            hp_percent = status["health_percent"]
            enemies = battle["matched_enemies"]
            current_counts = Counter(enemy["name"] for enemy in enemies)
            for creature, count in previous_counts.items():
                detected_deaths[creature] += max(0, count - current_counts[creature])
            for creature, count in current_counts.items():
                maximum_counts[creature] = max(maximum_counts[creature], count)
            previous_counts = current_counts
            emit(
                "scan",
                hp=hp_percent,
                mana=status["mana_percent"],
                entries=battle["visible_entries"],
                enemies=[enemy["name"] for enemy in enemies],
                silent_for=round(audio.silent_for(), 2),
            )

            if hp_percent < args.heal_below and time.monotonic() - last_heal >= 1.2:
                focus_game(hwnd)
                press_key(VK_O)
                heals += 1
                last_heal = time.monotonic()
                emit("healed", key="O", hp_before=hp_percent)

            if battle["empty"]:
                reason = "battle_list_empty"
                expected_corpses = {
                    creature: max(maximum_counts[creature], detected_deaths[creature])
                    for creature in maximum_counts
                    if creature in LOOTABLE_CREATURES
                    and max(maximum_counts[creature], detected_deaths[creature]) > 0
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
                    # Loot mexe no mouse/teclado: suspende o guard para nao roubar o clique.
                    fast_guard.suspended = True
                    try:
                        autoloot_result = perform_mapped_autoloot(
                            encounter_id=encounter_id,
                            current_screenshot=saved,
                            corpse_detection=corpse_detection,
                            reference_path=reference_path,
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
                    finally:
                        fast_guard.suspended = False
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
            point = click_target_and_fire(hwnd, saved, target)
            fast_guard.suppress_for(0.5)
            attacks += 1
            emit("attacked", target=target["name"], key="P", screen_click=point)
            # Loop curto: o guard ja faz insta-click em som novo, entao aqui so
            # mantemos o ataque no alvo atual e voltamos rapido ao rescan para
            # detectar morte / novo inimigo sem os 6s antigos de espera.
            fire_until = time.monotonic() + 2.5
            next_fire = time.monotonic() + 1.2
            loop_started = time.monotonic()
            while time.monotonic() < fire_until:
                now = time.monotonic()
                if audio.ever_heard_sound and audio.silent_for() >= args.silence:
                    emit("audio_silent_rescan", silent_for=round(audio.silent_for(), 2))
                    break
                if now - loop_started > 1.0 and audio.silent_for() < 0.3:
                    # Som fresco = algo aconteceu (dano/morte/novo agressor):
                    # o guard ja clicou no 1o slot, volta ao scan para confirmar.
                    emit("audio_fresh_rescan", silent_for=round(audio.silent_for(), 2))
                    break
                if now >= next_fire:
                    focus_game(hwnd)
                    press_key(VK_P)
                    fast_guard.suppress_for(0.5)
                    attacks += 1
                    emit("fired", target=target["name"], key="P")
                    next_fire = now + 1.2
                time.sleep(0.05)
    finally:
        readers.shutdown(wait=True, cancel_futures=True)
        try:
            fast_guard.stop()
        except Exception:
            pass
        audio.stop()
        audio.join(timeout=2)
        if chat_off_confirmed:
            focus_game(hwnd)
            press_key(VK_RETURN)

    try:
        fast_attacks = fast_guard.fast_attacks
    except Exception:
        fast_attacks = 0
    emit(
        "combat_loop_stopped",
        reason=reason,
        attacks=attacks,
        fast_attacks=fast_attacks,
        heals=heals,
        audio_peak=round(audio.peak_max, 6),
        chat="on" if chat_off_confirmed else "unknown",
        audio_error=audio.error,
        autoloot=autoloot_result,
        corpse_detection=corpse_detection,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
