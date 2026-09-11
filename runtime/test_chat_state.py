from __future__ import annotations

import unittest
from pathlib import Path

from runtime.chat_state import classify_chat_texts, read_chat_mode


ROOT = Path(__file__).resolve().parents[1]
CHAT_ON_FIXTURE = ROOT / "movement" / "captures" / "2026-09-10_215108165_Rafaelkrosa_Hotkey_6.png"


class ChatStateTests(unittest.TestCase):
    def test_classifies_obs_chat_off_ocr(self):
        self.assertEqual(classify_chat_texts(["ChatOF", "ChatO"]), "off")

    def test_classifies_chat_on_ocr(self):
        self.assertEqual(classify_chat_texts(["Chat on", "ChatOn"]), "on")

    def test_reads_chat_on_fixture(self):
        self.assertEqual(read_chat_mode(CHAT_ON_FIXTURE)["mode"], "on")


if __name__ == "__main__":
    unittest.main()
