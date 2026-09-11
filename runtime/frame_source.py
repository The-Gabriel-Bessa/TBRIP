"""Continuous frame source via OBS Virtual Camera (FFmpeg dshow).

Replaces the slow screenshot trigger cycle (Enter→*→Enter, ~6s)
with a continuous 30fps stream from OBS Game Capture.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


FFMPEG_PATH = r"C:\Users\bessa\Downloads\ffmpeg-8.1.2-full_build\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
VCAM_DEVICE = "OBS Virtual Camera"
VCAM_WIDTH = 1280
VCAM_HEIGHT = 720


class FrameSource:
    """Captures Tibia frames via OBS Virtual Camera in a background thread.

    Usage:
        source = FrameSource()
        source.start()
        frame = source.grab()           # latest frame as numpy BGR array
        path = source.grab_to_disk()    # save to disk, return Path
        pil = source.grab_pil()         # latest frame as PIL Image
        source.stop()
    """

    def __init__(
        self,
        ffmpeg_path: str = FFMPEG_PATH,
        device: str = VCAM_DEVICE,
        framerate: int = 30,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.device = device
        self.framerate = framerate

        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._latest_time: float = 0.0
        self._frame_count: int = 0
        self._running = False
        self._width = VCAM_WIDTH
        self._height = VCAM_HEIGHT
        self._captures_dir = Path(__file__).resolve().parent / "captures"

    @property
    def is_running(self) -> bool:
        return self._running and self._proc is not None and self._proc.poll() is None

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def _build_command(self) -> list[str]:
        return [
            self.ffmpeg_path, "-y",
            "-f", "dshow",
            "-framerate", str(self.framerate),
            "-video_size", f"{self._width}x{self._height}",
            "-i", f"video={self.device}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "pipe:1",
        ]

    def _reader_loop(self):
        """Background thread: read raw frames from FFmpeg stdout."""
        frame_bytes = self._width * self._height * 3
        while self._running and self._proc and self._proc.poll() is None:
            try:
                raw = self._proc.stdout.read(frame_bytes)
                if not raw or len(raw) != frame_bytes:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                    self._height, self._width, 3
                )
                with self._lock:
                    self._latest_frame = frame
                    self._latest_time = time.time()
                    self._frame_count += 1
            except Exception:
                break

        self._running = False

    def start(self) -> None:
        """Start the FFmpeg capture from OBS Virtual Camera."""
        if self.is_running:
            return

        print(f"FrameSource: starting capture from '{self.device}' ({self._width}x{self._height} @ {self.framerate}fps)")

        cmd = self._build_command()
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True, name="frame-source")
        self._thread.start()

        # Wait for first frame
        deadline = time.monotonic() + 5.0
        while self._latest_frame is None and time.monotonic() < deadline:
            time.sleep(0.05)

        if self._latest_frame is None:
            self.stop()
            raise TimeoutError(
                "FrameSource: no frame received within 5 seconds. "
                "Is OBS running with Virtual Camera enabled?"
            )

        print(f"FrameSource: first frame received (total: {self._frame_count})")

    def stop(self) -> None:
        """Stop the FFmpeg capture process."""
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def grab(self) -> np.ndarray:
        """Return the latest captured frame as a BGR numpy array."""
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("No frame available - is FrameSource started?")
            return self._latest_frame.copy()

    def grab_pil(self) -> Image.Image:
        """Return the latest captured frame as a PIL RGB Image."""
        frame = self.grab()
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def grab_to_disk(self, folder: Path | None = None) -> Path:
        """Save the latest frame to disk as PNG and return the path."""
        folder = folder or self._captures_dir
        folder.mkdir(parents=True, exist_ok=True)

        frame = self.grab()
        timestamp = int(self._latest_time * 1000)
        path = folder / f"stream_{timestamp}.png"
        cv2.imwrite(str(path), frame)
        return path

    def stats(self) -> dict:
        """Return capture statistics."""
        return {
            "running": self.is_running,
            "frame_count": self._frame_count,
            "latest_time": self._latest_time,
            "device": self.device,
            "size": f"{self._width}x{self._height}",
        }


def grab_single_frame(
    ffmpeg_path: str = FFMPEG_PATH,
    device: str = VCAM_DEVICE,
) -> tuple[np.ndarray, dict]:
    """Grab a single frame from OBS Virtual Camera. Convenience for one-shot use."""
    cmd = [
        ffmpeg_path, "-y",
        "-f", "dshow",
        "-i", f"video={device}",
        "-frames:v", "1",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-video_size", f"{VCAM_WIDTH}x{VCAM_HEIGHT}",
        "pipe:1",
    ]

    proc = subprocess.run(cmd, capture_output=True, timeout=10)
    expected = VCAM_WIDTH * VCAM_HEIGHT * 3

    if proc.returncode != 0 or len(proc.stdout) != expected:
        raise RuntimeError(f"grab_single_frame failed: got {len(proc.stdout)} bytes, expected {expected}")

    frame = np.frombuffer(proc.stdout, dtype=np.uint8).reshape(VCAM_HEIGHT, VCAM_WIDTH, 3)
    info = {"device": device, "width": VCAM_WIDTH, "height": VCAM_HEIGHT}
    return frame, info
