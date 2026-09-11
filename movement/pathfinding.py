"""Cardinal-only path planning over a persisted cave reference."""

from __future__ import annotations

from collections import deque

from movement.world_model import coordinate_key


CARDINAL_DIRECTIONS = {
    "W": (0, -1, 0),
    "A": (-1, 0, 0),
    "S": (0, 1, 0),
    "D": (1, 0, 0),
}
INITIAL_DEPARTURE = "DWWAA"


def destination(position: tuple[int, int, int], key: str) -> tuple[int, int, int]:
    dx, dy, dz = CARDINAL_DIRECTIONS[key]
    return position[0] + dx, position[1] + dy, position[2] + dz


def terrain_at(reference: dict, position: tuple[int, int, int]) -> str | None:
    return reference["tiles"].get(coordinate_key(position))


def expected_step(
    reference: dict,
    position: tuple[int, int, int],
    key: str,
    allow_blocked: bool,
    allowed_goal: tuple[int, int, int] | None = None,
) -> dict:
    target = destination(position, key)
    terrain = terrain_at(reference, target)
    if terrain == "walkable_green" or (target == allowed_goal and terrain == "stairs_up_yellow"):
        return {
            "key": key,
            "from": list(position),
            "requested": list(target),
            "expected": list(target),
            "terrain": terrain,
            "expected_result": "moved",
        }
    if terrain in {"blocked_gray", "blocked_red"} and allow_blocked:
        return {
            "key": key,
            "from": list(position),
            "requested": list(target),
            "expected": list(position),
            "terrain": terrain,
            "expected_result": "blocked",
        }
    raise RuntimeError(f"Movimento {key} recusado: destino {target} possui terreno {terrain!r}")


def reachable_paths(reference: dict, start: tuple[int, int, int], max_steps: int) -> dict[tuple[int, int, int], str]:
    paths = {start: ""}
    pending = deque([start])
    while pending:
        position = pending.popleft()
        path = paths[position]
        if len(path) >= max_steps:
            continue
        for key in "WASD":
            target = destination(position, key)
            if target in paths or terrain_at(reference, target) != "walkable_green":
                continue
            paths[target] = path + key
            pending.append(target)
    return paths


def shortest_path(
    reference: dict,
    start: tuple[int, int, int],
    goal: tuple[int, int, int],
    max_steps: int = 20,
) -> str | None:
    paths = {start: ""}
    pending = deque([start])
    while pending:
        position = pending.popleft()
        path = paths[position]
        if position == goal:
            return path
        if len(path) >= max_steps:
            continue
        for key in "WASD":
            target = destination(position, key)
            if target in paths:
                continue
            if target != goal and terrain_at(reference, target) != "walkable_green":
                continue
            paths[target] = path + key
            pending.append(target)
    return None


def path_positions(start: tuple[int, int, int], keys: str) -> list[tuple[int, int, int]]:
    positions = []
    position = start
    for key in keys:
        position = destination(position, key)
        positions.append(position)
    return positions


def initial_departure(reference: dict, start: tuple[int, int, int], max_steps: int = 5) -> dict:
    if start != (0, 0, 0):
        raise RuntimeError("A saida inicial so pode comecar em (0,0,0)")
    keys = INITIAL_DEPARTURE[:max_steps]
    position = start
    for key in keys:
        step = expected_step(reference, position, key, allow_blocked=False)
        position = tuple(step["expected"])
    return {
        "type": "initial_departure",
        "start": list(start),
        "goal": list(position),
        "keys": keys,
        "steps": len(keys),
    }


def attack_range_approach(
    reference: dict,
    player: tuple[int, int, int],
    target_offset: list[int],
    attack_range: int = 3,
    max_steps: int = 8,
) -> dict:
    target = (player[0] + target_offset[0], player[1] + target_offset[1], player[2])
    paths = reachable_paths(reference, player, max_steps)
    candidates = [
        position
        for position in paths
        if max(abs(position[0] - target[0]), abs(position[1] - target[1])) <= attack_range
    ]
    if not candidates:
        raise RuntimeError(f"Nenhum tile verde alcancavel dentro do alcance do alvo em {target}")
    goal = min(
        candidates,
        key=lambda position: (
            len(paths[position]),
            max(abs(position[0] - target[0]), abs(position[1] - target[1])),
        ),
    )
    return {
        "player": list(player),
        "target": list(target),
        "observed_offset": target_offset,
        "goal": list(goal),
        "keys": paths[goal],
        "steps": len(paths[goal]),
        "attack_range": attack_range,
    }


def combat_retreat_step(
    reference: dict,
    player: tuple[int, int, int],
    target_offsets: list[list[int]],
) -> dict:
    """Choose one green tile that maximizes distance from visible enemies."""
    if not target_offsets:
        raise RuntimeError("Nenhuma posicao de inimigo disponivel para recuo")

    targets = [
        (player[0] + offset[0], player[1] + offset[1], player[2])
        for offset in target_offsets
    ]

    def distances(position: tuple[int, int, int]) -> list[int]:
        return [
            max(abs(position[0] - target[0]), abs(position[1] - target[1]))
            for target in targets
        ]

    current_distances = distances(player)
    options = []
    for key in "WASD":
        goal = destination(player, key)
        if terrain_at(reference, goal) != "walkable_green":
            continue
        goal_distances = distances(goal)
        options.append((min(goal_distances), sum(goal_distances), key, goal))
    if not options:
        raise RuntimeError("Nenhum tile verde adjacente disponivel para recuo")

    clearance, total_distance, key, goal = max(options)
    if clearance < min(current_distances):
        raise RuntimeError("Todos os tiles de recuo aproximam o personagem dos inimigos")
    return {
        "start": list(player),
        "goal": list(goal),
        "keys": key,
        "current_clearance": min(current_distances),
        "clearance": clearance,
        "total_distance": total_distance,
        "target_offsets": target_offsets,
    }


def return_to_checkpoint(
    reference: dict,
    start: tuple[int, int, int],
    checkpoint: tuple[int, int, int],
    max_steps: int = 40,
) -> dict:
    keys = shortest_path(reference, start, checkpoint, max_steps)
    if keys is None:
        raise RuntimeError(f"Checkpoint {checkpoint} nao e alcancavel a partir de {start}")
    return {
        "type": "return_after_loot",
        "start": list(start),
        "goal": list(checkpoint),
        "keys": keys,
        "steps": len(keys),
    }


def directional_exploration(reference: dict, start: tuple[int, int, int], direction: str, max_steps: int) -> dict:
    paths = reachable_paths(reference, start, max_steps)
    dx, dy, _dz = CARDINAL_DIRECTIONS[direction]

    def progress(position: tuple[int, int, int]) -> int:
        return (position[0] - start[0]) * dx + (position[1] - start[1]) * dy

    candidates = [position for position in paths if progress(position) > 0]
    if not candidates:
        raise RuntimeError(f"Nenhum destino verde alcancavel na direcao {direction}")
    goal = max(
        candidates,
        key=lambda position: (
            progress(position),
            abs(position[0]) + abs(position[1]),
            len(paths[position]),
        ),
    )
    return {
        "start": list(start),
        "goal": list(goal),
        "keys": paths[goal],
        "steps": len(paths[goal]),
        "direction": direction,
        "directional_progress": progress(goal),
        "distance_from_origin": abs(goal[0]) + abs(goal[1]),
    }


def patrol_route(
    reference: dict,
    start: tuple[int, int, int],
    visits: dict[tuple[int, int, int], int],
    max_steps: int,
    recent: tuple[tuple[int, int, int], ...] = (),
) -> dict:
    paths = reachable_paths(reference, start, max_steps)
    candidates = [position for position, keys in paths.items() if keys]
    if not candidates:
        raise RuntimeError("Nenhum tile verde alcancavel para continuar a patrulha")

    def unknown_neighbors(position: tuple[int, int, int]) -> int:
        return sum(terrain_at(reference, destination(position, key)) is None for key in CARDINAL_DIRECTIONS)

    recent_weights = {position: index + 1 for index, position in enumerate(recent)}

    def recent_penalty(position: tuple[int, int, int]) -> int:
        return sum(recent_weights.get(step, 0) for step in path_positions(start, paths[position]))

    def immediate_reverse(position: tuple[int, int, int]) -> bool:
        steps = path_positions(start, paths[position])
        return len(recent) >= 2 and bool(steps) and steps[0] == recent[-2]

    goal = max(
        candidates,
        key=lambda position: (
            -immediate_reverse(position),
            -recent_penalty(position),
            -visits.get(position, 0),
            unknown_neighbors(position),
            len(paths[position]),
            abs(position[0]) + abs(position[1]),
        ),
    )
    return {
        "start": list(start),
        "goal": list(goal),
        "keys": paths[goal],
        "steps": len(paths[goal]),
        "previous_visits": visits.get(goal, 0),
        "recent_penalty": recent_penalty(goal),
        "immediate_reverse": immediate_reverse(goal),
        "unknown_neighbors": unknown_neighbors(goal),
    }
