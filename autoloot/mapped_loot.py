"""Approach detected corpses through mapped green tiles and quick-loot them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from autoloot.loot_once import perform_autoloot
from capture_internal import find_window
from movement.pathfinding import shortest_path, terrain_at
from movement.safe_walk import execute_sequence
from movement.world_model import analyze_world, localize_in_reference


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if TYPE_CHECKING:
    from runtime.frame_source import CaptureSession


ADJACENT_OFFSETS = (
    (0, -1, 0),
    (-1, 0, 0),
    (1, 0, 0),
    (0, 1, 0),
    (-1, -1, 0),
    (1, -1, 0),
    (-1, 1, 0),
    (1, 1, 0),
)


def plan_corpse_approach(
    reference: dict,
    player: tuple[int, int, int],
    corpse_offset: list[int],
    max_steps: int = 12,
) -> dict:
    corpse = (player[0] + corpse_offset[0], player[1] + corpse_offset[1], player[2])
    options = []
    for dx, dy, dz in ADJACENT_OFFSETS:
        goal = corpse[0] + dx, corpse[1] + dy, corpse[2] + dz
        if goal != player and terrain_at(reference, goal) != "walkable_green":
            continue
        keys = shortest_path(reference, player, goal, max_steps)
        if keys is None:
            continue
        options.append((len(keys), keys, goal))
    if not options:
        raise RuntimeError(f"Nenhum tile verde adjacente e alcancavel para o corpo em {corpse}")
    _length, keys, goal = min(options, key=lambda item: (item[0], item[1]))
    return {
        "player": list(player),
        "corpse": list(corpse),
        "goal": list(goal),
        "keys": keys,
        "steps": len(keys),
        "adjacent": max(abs(goal[0] - corpse[0]), abs(goal[1] - corpse[1])) == 1,
    }


def latest_screenshot(run: dict) -> Path:
    if run["steps"]:
        return Path(run["steps"][-1]["observed"]["image"])
    return Path(run["initial"]["image"])


def perform_mapped_autoloot(
    encounter_id: str,
    current_screenshot: Path,
    corpse_detection: dict,
    reference_path: Path,
    capture_session: CaptureSession | None = None,
    heal_below: float | None = None,
    emergency_hp: int | None = None,
    mana_below: float | None = None,
) -> dict:
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    analysis = analyze_world(current_screenshot, verify_name=False)
    localization = localize_in_reference(analysis, reference)
    if not localization["localized"]:
        return {"status": "aborted_unlocalized", "encounter_id": encounter_id}

    position = tuple(localization["coordinate"])
    corpse_coordinates = []
    for detection in corpse_detection.get("detections", []):
        offset = detection["tile_offset_from_player"]
        coordinate = (position[0] + offset[0], position[1] + offset[1], position[2])
        if coordinate not in corpse_coordinates:
            corpse_coordinates.append(coordinate)
    if not corpse_coordinates:
        return {"status": "no_corpses_detected", "encounter_id": encounter_id, "attempted": False}

    hwnd, _title = find_window("Tibia -")
    tibia_dir = Path.home() / "AppData" / "Local" / "Tibia" / "packages" / "Tibia"
    source_folder = tibia_dir / "screenshots"
    output_folder = PROJECT_ROOT / "runtime" / "captures"
    ledger_path = Path(__file__).resolve().parent / "loot_attempts.jsonl"
    results = []

    for index, corpse in enumerate(corpse_coordinates, start=1):
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        offset = [corpse[0] - position[0], corpse[1] - position[1]]
        try:
            plan = plan_corpse_approach(reference, position, offset)
        except RuntimeError as exc:
            results.append({"corpse": list(corpse), "status": "unreachable", "error": str(exc)})
            continue

        run, exit_code = execute_sequence(
            plan["keys"],
            position,
            reference_path,
            allow_blocked=False,
            capture_session=capture_session,
            heal_below=heal_below,
            emergency_hp=emergency_hp,
            mana_below=mana_below,
        )
        if exit_code != 0:
            results.append({"corpse": list(corpse), "status": "movement_aborted", "plan": plan, "run": run})
            break
        position = tuple(run["final_position"])
        current_screenshot = latest_screenshot(run)
        loot = perform_autoloot(
            hwnd=hwnd,
            encounter_id=f"{encounter_id}-corpse-{index}",
            current_screenshot=current_screenshot,
            source_folder=source_folder,
            output_folder=output_folder,
            ledger_path=ledger_path,
            capture_session=capture_session,
        )
        results.append({"corpse": list(corpse), "status": "attempted", "plan": plan, "loot": loot})

    attempted = sum(result["status"] == "attempted" for result in results)
    return {
        "status": "completed" if attempted == len(corpse_coordinates) else "partial",
        "encounter_id": encounter_id,
        "corpses": len(corpse_coordinates),
        "attempted": attempted,
        "final_position": list(position),
        "results": results,
    }
