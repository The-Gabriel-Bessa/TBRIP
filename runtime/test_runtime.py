from __future__ import annotations

import json
import unittest
from pathlib import Path

from runtime.coordinator import ActionCoordinator
from runtime.frame_pipeline import FramePipeline


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "movement" / "amazon_camp_cave_reference.json"
FIXTURE = ROOT / "movement" / "captures" / "2026-09-10_215108165_Rafaelkrosa_Hotkey_6.png"


class RuntimeTests(unittest.TestCase):
    def test_parallel_pipeline_uses_one_frame(self):
        reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        with FramePipeline(reference) as pipeline:
            snapshot, _analysis = pipeline.analyze(FIXTURE)

        self.assertEqual(snapshot["position"], [-4, -2, 0])
        self.assertEqual(snapshot["readers"], ["battle", "status", "world"])
        self.assertTrue(snapshot["battle_empty"])

    def test_action_priority(self):
        coordinator = ActionCoordinator(heal_below=70)
        base = {"health_percent": 100, "battle_empty": True}

        self.assertEqual(coordinator.decide({**base, "health_percent": 50}, loot_pending=True), "heal")
        self.assertEqual(coordinator.decide({**base, "battle_empty": False}, loot_pending=True), "combat")
        self.assertEqual(coordinator.decide({**base, "audio_alert": True}, loot_pending=True), "loot")
        self.assertEqual(coordinator.decide(base, loot_pending=True), "loot")
        self.assertEqual(coordinator.decide(base), "move")


if __name__ == "__main__":
    unittest.main()
