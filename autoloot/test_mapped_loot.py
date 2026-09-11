from __future__ import annotations

import json
import unittest
from pathlib import Path

from autoloot.mapped_loot import plan_corpse_approach


REFERENCE = Path(__file__).resolve().parents[1] / "movement" / "amazon_camp_cave_reference.json"


class MappedLootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    def test_approaches_east_corpse_with_wasd(self):
        plan = plan_corpse_approach(self.reference, (0, 0, 0), [4, 0])

        self.assertEqual(plan["keys"], "DDD")
        self.assertEqual(plan["goal"], [3, 0, 0])
        self.assertTrue(plan["adjacent"])

    def test_no_movement_when_already_adjacent(self):
        plan = plan_corpse_approach(self.reference, (1, 0, 0), [-1, 0])

        self.assertEqual(plan["keys"], "")
        self.assertEqual(plan["goal"], [1, 0, 0])


if __name__ == "__main__":
    unittest.main()
