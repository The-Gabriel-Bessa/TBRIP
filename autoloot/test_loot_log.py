from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from autoloot.loot_log import new_visible_lines, parse_line, parse_new_entries, terminal_entries
from autoloot.loot_once import append_ledger, attempted_encounters


class LootLogTests(unittest.TestCase):
    def test_parses_creature_and_items(self):
        result = parse_line("19:58 Loot of an amazon: a dagger, 5 gold coins. l�")

        self.assertEqual(result["type"], "loot_of")
        self.assertEqual(result["creature"], "amazon")
        self.assertEqual(result["items"], "a dagger, 5 gold coins")
        self.assertTrue(result["wanted_creature"])
        self.assertEqual(result["wanted_items"][0]["name"], "gold coin")
        self.assertEqual(result["wanted_items"][0]["quantity"], 5)

    def test_empty_results_are_terminal(self):
        entries = [
            parse_line("19:57 You looted none of the dropped items. (3 corpses)"),
            parse_line("19:57 You looted nothing from 3 corpses."),
        ]

        self.assertEqual([entry["type"] for entry in entries], ["none_collected", "nothing_found"])
        self.assertEqual(terminal_entries(entries), entries)

    def test_returns_only_new_lines(self):
        before = "19:57 You looted nothing from 3 corpses.\n19:58 Loot of an amazon: a dagger."
        after = "19:58 Loot of an amazon: a dagger.\n20:01 Loot of a valkyrie: 8 gold coins."

        self.assertEqual(new_visible_lines(before, after), ["20:01 Loot of a valkyrie: 8 gold coins."])
        parsed = parse_new_entries(before, after)
        self.assertEqual(parsed[0]["creature"], "valkyrie")

    def test_ignores_old_line_with_different_ocr_suffix(self):
        before = "22:49 Loot of an amazon: a brown bread, 3 gold coins, a skull. |"
        after = (
            "22:49 Loot of an amazon: a brown bread, 3 gold coins, a skull. [\n"
            "22:50 You looted nothing from 1 corpse. lv"
        )

        self.assertEqual(new_visible_lines(before, after), ["22:50 You looted nothing from 1 corpse. lv"])

    def test_full_container_is_server_log_noise(self):
        entry = parse_line("20:14 Attention! The container for unassigned loot is full.")

        self.assertEqual(entry["type"], "server_log_noise")
        self.assertEqual(terminal_entries([entry]), [])

    def test_extracts_all_wanted_items(self):
        entry = parse_line(
            "20:15 Loot of a witch: a broom, a protective charm, "
            "2 girlish hair decorations, 17 gold coins."
        )

        self.assertEqual(
            [(item["name"], item["quantity"]) for item in entry["wanted_items"]],
            [
                ("gold coin", 17),
                ("broom", 1),
                ("protective charm", 1),
                ("girlish hair decoration", 2),
            ],
        )

    def test_ledger_prevents_reusing_encounter_id(self):
        with TemporaryDirectory() as folder:
            ledger = Path(folder) / "attempts.jsonl"
            append_ledger(ledger, {"encounter_id": "combat-123", "status": "confirmed"})

            self.assertEqual(attempted_encounters(ledger), {"combat-123"})


if __name__ == "__main__":
    unittest.main()
