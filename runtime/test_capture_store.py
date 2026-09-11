from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.capture_store import store_generated_screenshot


class CaptureStoreTests(unittest.TestCase):
    def test_moves_generated_files_into_bounded_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_folder = root / "source"
            output_folder = root / "output"
            source_folder.mkdir()

            for index in range(3):
                source = source_folder / f"{index}.png"
                source.write_bytes(str(index).encode("ascii"))
                destination = store_generated_screenshot(source, output_folder, keep=2)
                self.assertTrue(destination.exists())
                self.assertFalse(source.exists())

            self.assertEqual(len(list(output_folder.glob("*.png"))), 2)


if __name__ == "__main__":
    unittest.main()
