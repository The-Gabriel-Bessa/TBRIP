"""Execute a WASD sequence and verify every result against the minimap."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from capture_internal import find_window, focus_window, trigger_screenshot_with_retry  # noqa: E402
from movement.pathfinding import CARDINAL_DIRECTIONS, expected_step  # noqa: E402
from movement.world_model import localize_in_reference, merge_observation  # noqa: E402
from runtime.chat_state import ensure_chat_off  # noqa: E402
from runtime.coordinator import resource_action  # noqa: E402
from runtime.frame_source import CAPTURE_MODES, VCAM_DEVICE, CaptureSession  # noqa: E402
from runtime.frame_pipeline import FramePipeline  # noqa: E402
from runtime.capture_store import store_generated_screenshot  # noqa: E402


user32 = ctypes.windll.user32
VIRTUAL_KEYS = {key: ord(key) for key in CARDINAL_DIRECTIONS}
KEYEVENTF_KEYUP = 0x0002


def parse_coordinate(raw: str) -> tuple[int, int, int]:
    values = tuple(int(value.strip()) for value in raw.split(","))
    if len(values) != 3:
        raise argparse.ArgumentTypeError("Use x,y,z")
    return values


def capture_state(
    hwnd: int,
    source_folder: Path,
    output_folder: Path,
    pipeline: FramePipeline,
    capture_session: CaptureSession | None = None,
) -> tuple[dict, dict]:
    if capture_session is not None:
        _image, result = capture_session.capture_and_analyze(
            hwnd,
            source_folder,
            output_folder,
            pipeline.analyze,
        )
        return result
    source = trigger_screenshot_with_retry(hwnd, source_folder)
    image = store_generated_screenshot(source, output_folder)
    return pipeline.analyze(image)


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def press_movement_key(hwnd: int, key: str) -> None:
    virtual_key = VIRTUAL_KEYS[key]
    focus_window(hwnd)
    try:
        user32.keybd_event(virtual_key, 0, 0, 0)
        time.sleep(0.06)
    finally:
        user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)


def command_groups(sequence: str, verify_every: int, allow_blocked: bool) -> list[str]:
    group_size = 1 if allow_blocked else max(1, verify_every)
    return [sequence[index : index + group_size] for index in range(0, len(sequence), group_size)]


def execute_sequence(
    sequence: str,
    start: tuple[int, int, int],
    reference_path: Path,
    allow_blocked: bool,
    verify_every: int = 1,
    initial_state: dict | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    stop_on_enemies: bool = True,
    allowed_goal: tuple[int, int, int] | None = None,
    capture_session: CaptureSession | None = None,
    heal_below: float | None = None,
    emergency_hp: int | None = None,
) -> tuple[dict, int]:
    invalid = sorted(set(sequence) - set(CARDINAL_DIRECTIONS))
    if invalid:
        raise RuntimeError(f"Sequencia possui teclas invalidas: {invalid}")

    project = Path(__file__).resolve().parent
    output_folder = PROJECT_ROOT / "runtime" / "captures"
    runs_folder = project / "runs"
    source_folder = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia" / "screenshots"
    output_folder.mkdir(parents=True, exist_ok=True)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    hwnd, title = find_window("Tibia -")
    run = {
        "window": title,
        "sequence": sequence,
        "required_start": list(start),
        "allow_blocked": allow_blocked,
        "verify_every": verify_every,
        "stop_on_enemies": stop_on_enemies,
        "allowed_goal": None if allowed_goal is None else list(allowed_goal),
        "steps": [],
        "completed": False,
    }
    run_path = runs_folder / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{sequence}.json"

    def pending_resource(state: dict) -> str | None:
        if heal_below is None and emergency_hp is None:
            return None
        return resource_action(
            state,
            heal_below=-1 if heal_below is None else heal_below,
            emergency_hp=-1 if emergency_hp is None else emergency_hp,
        )

    def interrupt_for_resource(state: dict, position: tuple[int, int, int]) -> tuple[dict, int] | None:
        action = pending_resource(state)
        if action is None:
            return None
        run["interrupted_for_resource"] = action
        if action in {"heal", "emergency_heal"}:
            run["interrupted_for_heal"] = True
        run["final_position"] = list(position)
        return run, 3

    pipeline = FramePipeline(reference)
    try:
        if initial_state is None:
            state, analysis = capture_state(
                hwnd,
                source_folder,
                output_folder,
                pipeline,
                capture_session,
            )
        else:
            state = dict(initial_state)
            analysis = None
        run["initial"] = state
        if capture_session is not None:
            run["chat"] = ensure_chat_off(
                hwnd,
                Path(state["image"]),
                capture_session,
                source_folder,
                output_folder,
            )
        if not state["localized"] or state["position"] != list(start):
            raise RuntimeError(f"Posicao inicial esperada {list(start)}, observada {state['position']}")
        if stop_on_enemies and not state["battle_empty"]:
            raise RuntimeError(f"Battle List nao esta vazia: {state['enemies']}")
        resource_interrupt = interrupt_for_resource(state, start)
        if resource_interrupt is not None:
            return resource_interrupt
        if analysis is not None:
            localization = localize_in_reference(analysis, reference)
            merge_observation(reference, analysis, localization)
            reference_path.write_text(json.dumps(reference, indent=2) + "\n", encoding="ascii")

        position = start
        command_index = 0
        groups = command_groups(sequence, verify_every, allow_blocked)
        while groups:
            group = groups.pop(0)
            group_start = position
            plans = []
            planned_position = position
            for key in group:
                planned = expected_step(
                    reference,
                    planned_position,
                    key,
                    allow_blocked,
                    allowed_goal=allowed_goal,
                )
                plans.append(planned)
                planned_position = tuple(planned["expected"])

            focus_window(hwnd)
            time.sleep(0.25)
            sent_plans = []
            interrupted_by_audio = False
            for planned in plans:
                press_movement_key(hwnd, planned["key"])
                sent_plans.append(planned)
                command_index += 1
                time.sleep(0.4)
                if interrupt_check is not None and interrupt_check():
                    interrupted_by_audio = True
                    break
            if len(sent_plans) < len(plans):
                unsent = "".join(plan["key"] for plan in plans[len(sent_plans) :])
                groups.insert(0, unsent)

            expected_position = tuple(sent_plans[-1]["expected"])
            state, analysis = capture_state(
                hwnd,
                source_folder,
                output_folder,
                pipeline,
                capture_session,
            )
            step = {
                "index": len(run["steps"]) + 1,
                "command_indexes": [command_index - len(sent_plans) + 1, command_index],
                "keys": "".join(plan["key"] for plan in sent_plans),
                "from": list(group_start),
                "expected": list(expected_position),
                "path": [plan["expected"] for plan in sent_plans],
                "moved_count": sum(plan["expected_result"] == "moved" for plan in sent_plans),
                "expected_results": [plan["expected_result"] for plan in sent_plans],
                "interrupted_by_audio": interrupted_by_audio,
                "observed": state,
            }
            run["steps"].append(step)
            if not state["localized"]:
                raise RuntimeError(f"Grupo {step['keys']}: localizacao ambigua")
            if state["position"] != list(expected_position):
                raise RuntimeError(
                    f"Grupo {step['keys']}: esperado {list(expected_position)}, observado {state['position']}"
                )
            localization = localize_in_reference(analysis, reference)
            merge_observation(reference, analysis, localization)
            reference_path.write_text(json.dumps(reference, indent=2) + "\n", encoding="ascii")
            position = tuple(state["position"])
            if stop_on_enemies and not state["battle_empty"]:
                raise RuntimeError(f"Grupo {step['keys']}: inimigos detectados {state['enemies']}")
            resource_interrupt = interrupt_for_resource(state, position)
            if resource_interrupt is not None:
                return resource_interrupt

        run["completed"] = True
        run["final_position"] = list(position)
        return run, 0
    except Exception as exc:
        run["error"] = f"{type(exc).__name__}: {exc}"
        return run, 2
    finally:
        pipeline.close()
        run["log"] = str(run_path.resolve())
        save_json(run_path, run)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sequence", help="Sequencia contendo somente W, A, S e D")
    parser.add_argument("--start", type=parse_coordinate, required=True)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path(__file__).resolve().parent / "amazon_camp_cave_reference.json",
    )
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--verify-every", type=int, default=1)
    parser.add_argument("--capture-source", choices=CAPTURE_MODES, default="auto")
    parser.add_argument("--obs-device", default=VCAM_DEVICE)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    if args.verify_every < 1:
        parser.error("--verify-every deve ser pelo menos 1")

    hwnd, _title = find_window("Tibia -")
    with CaptureSession.for_window(
        hwnd,
        mode=args.capture_source,
        ffmpeg_path=args.ffmpeg,
        device=args.obs_device,
    ) as capture_session:
        run, exit_code = execute_sequence(
            args.sequence.upper(),
            args.start,
            args.reference,
            args.allow_blocked,
            verify_every=args.verify_every,
            capture_session=capture_session,
        )
    print(json.dumps(run, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
