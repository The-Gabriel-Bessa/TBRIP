from __future__ import annotations

import json
import unittest
from pathlib import Path

from movement.pathfinding import (
    attack_range_approach,
    combat_retreat_step,
    directional_exploration,
    expected_step,
    initial_departure,
    patrol_route,
    return_to_checkpoint,
)
from movement.safe_walk import command_groups


REFERENCE = Path(__file__).parent / "amazon_camp_cave_reference.json"


class PathfindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    def test_requested_sequence_moves_then_hits_gray_wall(self):
        position = (0, 0, 0)
        results = []
        for key in "SDWWAAA":
            step = expected_step(self.reference, position, key, allow_blocked=True)
            position = tuple(step["expected"])
            results.append(step["expected_result"])

        self.assertEqual(results, ["moved"] * 4 + ["blocked"] * 3)
        self.assertEqual(position, (1, -1, 0))

    def test_plans_westward_detour_using_only_green(self):
        plan = directional_exploration(self.reference, (1, -1, 0), "A", max_steps=6)

        self.assertEqual(plan["keys"], "WAAAAA")
        self.assertEqual(plan["goal"], [-4, -2, 0])

    def test_patrol_prefers_unvisited_green_tiles(self):
        plan = patrol_route(self.reference, (0, 0, 0), {(1, 0, 0): 3}, max_steps=4)

        self.assertGreater(plan["steps"], 0)
        self.assertLessEqual(plan["steps"], 4)
        self.assertNotEqual(plan["goal"], [1, 0, 0])

    def test_initial_departure_uses_configured_route(self):
        plan = initial_departure(self.reference, (0, 0, 0))

        self.assertEqual(plan["keys"], "DWWAA")
        self.assertEqual(plan["goal"], [-1, -2, 0])

    def test_patrol_avoids_immediate_reverse_when_another_route_exists(self):
        reference = {
            "tiles": {
                "-1,0,0": "walkable_green",
                "1,0,0": "walkable_green",
            }
        }
        plan = patrol_route(reference, (0, 0, 0), {}, 1, ((-1, 0, 0), (0, 0, 0)))

        self.assertEqual(plan["keys"], "D")
        self.assertFalse(plan["immediate_reverse"])

    def test_patrol_groups_two_commands_per_visual_check(self):
        self.assertEqual(command_groups("DWWAA", 2, allow_blocked=False), ["DW", "WA", "A"])
        self.assertEqual(command_groups("AAA", 2, allow_blocked=True), ["A", "A", "A"])

    def test_plans_chase_until_target_is_in_range(self):
        plan = attack_range_approach(self.reference, (0, 0, 0), [6, 1], attack_range=3)

        self.assertGreater(plan["steps"], 0)
        self.assertLessEqual(plan["steps"], 3)

    def test_returns_to_precombat_checkpoint(self):
        plan = return_to_checkpoint(self.reference, (3, 0, 0), (1, -1, 0))

        self.assertEqual(plan["goal"], [1, -1, 0])
        self.assertGreater(plan["steps"], 0)

    def test_can_return_to_yellow_origin(self):
        plan = return_to_checkpoint(self.reference, (3, 0, 0), (0, 0, 0))

        self.assertEqual(plan["keys"], "AAA")
        final_step = expected_step(
            self.reference,
            (1, 0, 0),
            "A",
            allow_blocked=False,
            allowed_goal=(0, 0, 0),
        )
        self.assertEqual(final_step["expected"], [0, 0, 0])

    def test_retreat_chooses_tile_farthest_from_enemies(self):
        reference = {
            "tiles": {
                "-1,0,0": "walkable_green",
                "1,0,0": "walkable_green",
                "0,-1,0": "walkable_green",
            }
        }
        retreat = combat_retreat_step(reference, (0, 0, 0), [[2, 0]])

        self.assertIn(retreat["keys"], {"A", "W"})
        self.assertGreaterEqual(retreat["clearance"], 1)


if __name__ == "__main__":
    unittest.main()
