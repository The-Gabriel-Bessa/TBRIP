from __future__ import annotations

import unittest

from autoloot.approach_plan import plan_to_adjacent


class ApproachPlanTests(unittest.TestCase):
    def test_cardinal_path_stops_adjacent(self):
        result = plan_to_adjacent([-4, 0])

        self.assertEqual(result["keys"], ["A", "A", "A"])
        self.assertEqual(result["expected_final_offset"], [-1, 0])
        self.assertTrue(result["adjacent"])

    def test_diagonal_path_stops_adjacent(self):
        result = plan_to_adjacent([-2, 3])

        self.assertEqual(result["keys"], ["Z", "Z"])
        self.assertEqual(result["expected_final_offset"], [0, 1])
        self.assertTrue(result["adjacent"])


if __name__ == "__main__":
    unittest.main()
