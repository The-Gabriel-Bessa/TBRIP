from __future__ import annotations

import copy
import unittest
from pathlib import Path

from movement.world_model import (
    analyze_world,
    classify_tile,
    gameplay_point,
    localize_in_reference,
    make_reference,
    merge_observation,
    parse_coordinate,
)

import numpy as np


FIXTURE = Path(__file__).parent / "captures" / "2026-09-10_210004080_Rafaelkrosa_Hotkey_6.png"


class WorldModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = analyze_world(FIXTURE, verify_name=False)

    def test_finds_player_as_origin(self):
        self.assertEqual(self.analysis["origin"]["coordinate"], [0, 0, 0])
        self.assertEqual(self.analysis["minimap"]["tile_size"], 4)
        self.assertEqual(self.analysis["minimap"]["player_marker"]["component_area"], 20)
        self.assertEqual(self.analysis["minimap"]["tiles"][(0, 0, 0)]["terrain"], "player")

    def test_classifies_cave_terrain(self):
        tiles = self.analysis["minimap"]["tiles"]
        self.assertEqual(tiles[(1, 0, 0)]["terrain"], "walkable_green")
        self.assertEqual(tiles[(-1, 0, 0)]["terrain"], "blocked_gray")
        self.assertEqual(tiles[(3, -2, 0)]["terrain"], "blocked_red")
        self.assertEqual(self.analysis["stairs"], [])

        yellow = np.full((4, 4, 3), (255, 255, 0), dtype=np.uint8)
        self.assertEqual(classify_tile(yellow), ("stairs_up_yellow", 16))

    def test_maps_visible_coordinate_to_gameplay(self):
        center = self.analysis["gameplay"]["center"]
        self.assertEqual(center, [624, 302])
        self.assertEqual(gameplay_point(center, (1, 2, 0)), [668, 390])
        self.assertIsNone(gameplay_point(center, (8, 0, 0)))

    def test_localizes_origin_in_its_reference(self):
        reference = make_reference(self.analysis)
        result = localize_in_reference(self.analysis, reference)
        self.assertTrue(result["localized"])
        self.assertEqual(result["coordinate"], [0, 0, 0])
        self.assertEqual(result["best"]["agreement"], 1.0)

    def test_localizes_a_simulated_step_east(self):
        reference = make_reference(self.analysis)
        reference_map = {parse_coordinate(key): terrain for key, terrain in reference["tiles"].items()}
        shifted = copy.deepcopy(self.analysis)
        for (dx, dy, _z), tile in shifted["minimap"]["tiles"].items():
            if (dx, dy) == (0, 0):
                continue
            tile["terrain"] = reference_map.get((dx + 1, dy, 0), "unknown")

        result = localize_in_reference(shifted, reference)

        self.assertTrue(result["localized"])
        self.assertEqual(result["coordinate"], [1, 0, 0])

        update = merge_observation(reference, shifted, result)
        self.assertGreater(update["confirmed_tiles"], 0)
        self.assertEqual(update["conflicts"], 0)
        self.assertEqual(reference["observations"][0]["coordinate"], [1, 0, 0])


if __name__ == "__main__":
    unittest.main()
