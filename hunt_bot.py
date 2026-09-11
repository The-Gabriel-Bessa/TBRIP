"""Coordinate parallel readers, combat, mapped autoloot, and green-tile patrol."""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

from capture_internal import find_window, press_key
from movement.pathfinding import initial_departure, patrol_route, return_to_checkpoint
from movement.safe_walk import capture_state, execute_sequence
from movement.world_model import localize_in_reference, merge_observation
from runtime.chat_state import ensure_chat_off
from runtime.coordinator import ActionCoordinator
from runtime.frame_pipeline import FramePipeline
from runtime.frame_source import CAPTURE_MODES, VCAM_DEVICE, CaptureSession


user32 = ctypes.windll.user32
VK_O = 0x4F


def latest_state(run: dict) -> dict:
    if run["steps"]:
        return run["steps"][-1]["observed"]
    return run["initial"]


def run_combat_process(
    project: Path,
    autoloot: bool,
    capture_source: str,
    obs_device: str,
    ffmpeg: str | None,
) -> dict:
    command = [
        sys.executable,
        str(project / "combat_until_clear.py"),
        "--max-seconds",
        "60",
        "--heal-below",
        "70",
        "--capture-source",
        capture_source,
        "--obs-device",
        obs_device,
    ]
    if ffmpeg:
        command.extend(["--ffmpeg", ffmpeg])
    if not autoloot:
        command.append("--no-autoloot")
    process = subprocess.Popen(
        command,
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    events = []
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event": "raw_output", "text": line})
    exit_code = process.wait()
    return {"exit_code": exit_code, "events": events}


def save_run(path: Path, run: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-moves", type=int, default=30)
    parser.add_argument("--segment-steps", type=int, default=15)
    parser.add_argument("--verify-every", type=int, default=1)
    parser.add_argument("--heal-below", type=float, default=70.0)
    parser.add_argument("--autoloot", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--capture-source", choices=CAPTURE_MODES, default="auto")
    parser.add_argument("--obs-device", default=VCAM_DEVICE)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()

    project = Path(__file__).resolve().parent
    movement_dir = project / "movement"
    reference_path = movement_dir / "amazon_camp_cave_reference.json"
    source_folder = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia" / "screenshots"
    output_folder = project / "runtime" / "captures"
    run_path = project / "runs" / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_hunt.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    coordinator = ActionCoordinator(args.heal_below)
    hwnd, title = find_window("Tibia -")
    capture_session = CaptureSession.for_window(
        hwnd,
        mode=args.capture_source,
        ffmpeg_path=args.ffmpeg,
        device=args.obs_device,
    )
    visits: Counter = Counter()
    recent = deque(maxlen=20)
    run = {
        "window": title,
        "max_moves": args.max_moves,
        "segment_steps": args.segment_steps,
        "verify_every": args.verify_every,
        "autoloot": args.autoloot,
        "capture_source": args.capture_source,
        "segments": [],
        "combats": [],
        "completed": False,
    }
    moves = 0
    pending_return: tuple[int, int, int] | None = None

    try:
        capture_session.start()
        with FramePipeline(reference) as pipeline:
            state, analysis = capture_state(
                hwnd,
                source_folder,
                output_folder,
                pipeline,
                capture_session,
            )
        run["chat"] = ensure_chat_off(
            hwnd,
            Path(state["image"]),
            capture_session,
            source_folder,
            output_folder,
        )
        if not state["localized"]:
            raise RuntimeError("Posicao inicial nao localizada")
        position = tuple(state["position"])
        run["initial"] = state
        visits[position] += 1
        recent.append(position)
        startup_pending = position == (0, 0, 0)
        merge_observation(reference, analysis, localize_in_reference(analysis, reference))
        reference_path.write_text(json.dumps(reference, indent=2) + "\n", encoding="ascii")

        while args.max_moves > 0 and (
            moves < args.max_moves or not state["battle_empty"] or pending_return is not None
        ):
            if pending_return == position and state["battle_empty"]:
                pending_return = None
            decision = coordinator.decide(state)
            run["segments"].append(
                {
                    "type": "decision",
                    "frame_id": state["frame_id"],
                    "decision": decision,
                    "position": state["position"],
                }
            )

            if decision == "heal":
                with coordinator.action("heal", state["frame_id"]):
                    user32.SwitchToThisWindow(hwnd, True)
                    time.sleep(0.2)
                    press_key(VK_O)
                time.sleep(0.8)
            elif decision == "combat":
                if pending_return is None:
                    pending_return = position
                    run["segments"].append(
                        {
                            "type": "combat_checkpoint",
                            "position": list(pending_return),
                            "frame_id": state["frame_id"],
                        }
                    )
                # O subprocesso de combate detecta inimigos via frame
                with coordinator.action("combat", state["frame_id"]):
                    resume_obs = capture_session.uses_obs
                    child_capture_source = args.capture_source if resume_obs else "screenshot"
                    if resume_obs:
                        capture_session.stop()
                    try:
                        combat = run_combat_process(
                            project,
                            args.autoloot,
                            child_capture_source,
                            args.obs_device,
                            args.ffmpeg,
                        )
                    finally:
                        if resume_obs:
                            time.sleep(0.15)
                            capture_session.start()
                run["combats"].append(combat)
                if combat["exit_code"] != 0:
                    raise RuntimeError(f"Combate terminou com codigo {combat['exit_code']}")
            else:
                reference = json.loads(reference_path.read_text(encoding="utf-8"))
                remaining = min(args.segment_steps, args.max_moves - moves)
                if pending_return is not None:
                    plan = return_to_checkpoint(reference, position, pending_return)
                    movement_type = "return_after_loot"
                elif startup_pending and position == (0, 0, 0):
                    plan = initial_departure(reference, position, min(5, args.max_moves - moves))
                    startup_pending = False
                    movement_type = "initial_departure"
                else:
                    startup_pending = False
                    plan = patrol_route(reference, position, visits, remaining, tuple(recent))
                    movement_type = "patrol"
                with coordinator.action("move", state["frame_id"]):
                    movement, exit_code = execute_sequence(
                        plan["keys"],
                        position,
                        reference_path,
                        allow_blocked=False,
                        verify_every=args.verify_every,
                        initial_state=state,
                        interrupt_check=None,
                        allowed_goal=pending_return if movement_type == "return_after_loot" else None,
                        capture_session=capture_session,
                    )
                run["segments"].append(
                    {"type": "movement", "movement_type": movement_type, "plan": plan, "run": movement}
                )
                state = latest_state(movement)
                for step in movement["steps"]:
                    if movement_type != "return_after_loot":
                        moves += step["moved_count"]
                    for observed_position in step["path"]:
                        observed = tuple(observed_position)
                        visits[observed] += 1
                        recent.append(observed)
                position = tuple(state["position"])
                if movement_type == "return_after_loot" and exit_code == 0 and position == pending_return:
                    pending_return = None
                if exit_code == 0:
                    continue
                if state["battle_empty"]:
                    raise RuntimeError(movement.get("error", "Movimento abortado"))

            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            with FramePipeline(reference) as pipeline:
                state, _analysis = capture_state(
                    hwnd,
                    source_folder,
                    output_folder,
                    pipeline,
                    capture_session,
                )
            if not state["localized"]:
                raise RuntimeError("Posicao perdida depois da acao")
            position = tuple(state["position"])
            visits[position] += 1
            recent.append(position)

        run["completed"] = True
        run["final_position"] = list(position)
        run["moves"] = moves
        run["pending_return"] = None if pending_return is None else list(pending_return)
        run["recent_positions"] = [list(position) for position in recent]
        return 0
    except Exception as exc:
        run["error"] = f"{type(exc).__name__}: {exc}"
        return 2
    finally:
        run["capture"] = capture_session.stats()
        capture_session.stop()
        run["log"] = str(run_path.resolve())
        save_run(run_path, run)
        print(json.dumps({"event": "hunt_stopped", **run}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
