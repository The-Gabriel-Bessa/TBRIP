from __future__ import annotations

import unittest

import numpy as np

from movement.world_model import classify_tile, find_player_marker
from read_status_bars import find_bar_pairs
from runtime.frame_source import CaptureSession, fit_frame_to_size, resolve_ffmpeg


class FrameSourceTests(unittest.TestCase):
    def test_crops_center_before_restoring_client_size(self):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        for row in range(10):
            frame[row, :, :] = row

        fitted = fit_frame_to_size(frame, (10, 5))

        self.assertEqual(fitted.shape, (5, 10, 3))
        self.assertTrue(np.all(fitted[0] == 2))
        self.assertTrue(np.all(fitted[-1] == 6))

    def test_rejects_unknown_capture_mode(self):
        with self.assertRaises(ValueError):
            CaptureSession(mode="unknown")

    def test_rejects_missing_explicit_ffmpeg(self):
        with self.assertRaises(FileNotFoundError):
            resolve_ffmpeg("definitely-missing-ffmpeg.exe")

    def test_finds_status_bars_after_obs_color_conversion(self):
        pixels = np.zeros((100, 160, 3), dtype=np.uint8)
        pixels[40:43, 60:88] = (15, 237, 5)
        pixels[44:48, 60:88] = (5, 20, 236)

        pairs = find_bar_pairs(pixels)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0]["fill"], 28)
        self.assertEqual(pairs[0][1]["fill"], 28)

    def test_finds_obs_near_white_player_marker(self):
        pixels = np.zeros((20, 20, 3), dtype=np.uint8)
        pixels[8:13, 8:13] = (235, 235, 235)

        marker = find_player_marker(pixels, [100, 200, 120, 220])

        self.assertEqual(marker["component_area"], 25)
        self.assertEqual(marker["screenshot_center"], [110.0, 210.0])

    def test_classifies_obs_shifted_minimap_green(self):
        tile = np.full((4, 4, 3), (15, 237, 5), dtype=np.uint8)

        terrain, matching_pixels = classify_tile(tile)

        self.assertEqual(terrain, "walkable_green")
        self.assertEqual(matching_pixels, 16)


if __name__ == "__main__":
    unittest.main()
