"""Plan keyboard steps that end adjacent to a corpse tile."""

from __future__ import annotations

import argparse
import json


DIRECTIONS = {
    (-1, -1): "Q",
    (0, -1): "W",
    (1, -1): "E",
    (-1, 0): "A",
    (1, 0): "D",
    (-1, 1): "Z",
    (0, 1): "S",
    (1, 1): "C",
}


def sign(value: int) -> int:
    return (value > 0) - (value < 0)


def plan_to_adjacent(tile_offset: list[int], max_steps: int = 12) -> dict:
    target_x, target_y = tile_offset
    remaining_x, remaining_y = target_x, target_y
    keys = []

    while max(abs(remaining_x), abs(remaining_y)) > 1 and len(keys) < max_steps:
        move_x = sign(remaining_x)
        move_y = sign(remaining_y)
        key = DIRECTIONS[(move_x, move_y)]
        keys.append(key)
        remaining_x -= move_x
        remaining_y -= move_y

    return {
        "target_offset": [target_x, target_y],
        "keys": keys,
        "planned_steps": len(keys),
        "expected_final_offset": [remaining_x, remaining_y],
        "adjacent": max(abs(remaining_x), abs(remaining_y)) <= 1,
        "requires_step_verification": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dx", type=int)
    parser.add_argument("dy", type=int)
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(plan_to_adjacent([args.dx, args.dy], args.max_steps), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
