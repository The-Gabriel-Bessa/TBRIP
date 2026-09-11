from __future__ import annotations

import unittest
from pathlib import Path

from combat_feedback import is_destination_out_of_range, read_combat_feedback


FIXTURE = Path(__file__).parent / "runtime" / "captures" / "2026-09-10_223302128_Rafaelkrosa_Hotkey_6.png"
NO_MESSAGE_FIXTURE = Path(__file__).parent / "runtime" / "captures" / "2026-09-10_223315176_Rafaelkrosa_Hotkey_6.png"


class CombatFeedbackTests(unittest.TestCase):
    def test_normalizes_ocr_spacing(self):
        self.assertTrue(is_destination_out_of_range("Destination isoutofrange"))
        self.assertTrue(is_destination_out_of_range("Destination is nit ak range."))
        self.assertFalse(is_destination_out_of_range("You are exhausted."))

    def test_detects_destination_out_of_range(self):
        if not FIXTURE.exists():
            self.skipTest("Rolling runtime fixture was pruned")
        result = read_combat_feedback(FIXTURE)

        self.assertTrue(result["destination_out_of_range"])

    def test_does_not_chase_without_feedback_message(self):
        if not NO_MESSAGE_FIXTURE.exists():
            self.skipTest("Rolling runtime fixture was pruned")
        result = read_combat_feedback(NO_MESSAGE_FIXTURE)

        self.assertFalse(result["destination_out_of_range"])


if __name__ == "__main__":
    unittest.main()
