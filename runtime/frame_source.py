"""Low-latency frames from OBS Virtual Camera with screenshot fallback."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable, TypeVar

import cv2
import numpy as np
from PIL import Image


DEFAULT_FFMPEG_PATH = Path(
    r"C:\Users\bessa\Downloads\ffmpeg-8.1.2-full_build\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
)
VCAM_DEVICE = "OBS Virtual Camera"
VCAM_WIDTH = 1280
VCAM_HEIGHT = 720
CAPTURE_MODES = ("auto", "obs", "screenshot")

T = TypeVar("T")


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def resolve_ffmpeg(explicit: str | Path | None = None) -> str:
    """Resolve FFmpeg from CLI, environment, PATH, or the known local install."""
    if explicit:
        explicit_path = Path(explicit).expanduser()
        explicit_command = shutil.which(str(explicit))
        if explicit_path.is_file():
            return str(explicit_path.resolve())
        if explicit_command:
            return str(Path(explicit_command).resolve())
        raise FileNotFoundError(f"FFmpeg informado nao encontrado: {explicit}")

    candidates = [
        os.environ.get("TIBIARIP_FFMPEG"),
        shutil.which("ffmpeg"),
        DEFAULT_FFMPEG_PATH,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
    raise FileNotFoundError(
        "FFmpeg nao encontrado. Use --ffmpeg, TIBIARIP_FFMPEG ou adicione ffmpeg ao PATH."
    )


def client_size(hwnd: int) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if (width <= 0 or height <= 0) and user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
        time.sleep(0.2)
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError()
        width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Area cliente do Tibia invalida: {width}x{height}")
    return width, height


def fit_frame_to_size(frame: np.ndarray, target_size: tuple[int, int] | None) -> np.ndarray:
    """Remove OBS fit-to-canvas bars and restore client-space coordinates."""
    if target_size is None:
        return frame
    target_width, target_height = target_size
    if target_width <= 0 or target_height <= 0:
        raise ValueError(f"Tamanho de destino invalido: {target_size}")

    height, width = frame.shape[:2]
    source_ratio = width / height
    target_ratio = target_width / target_height
    if source_ratio > target_ratio:
        content_width = max(1, round(height * target_ratio))
        left = (width - content_width) // 2
        frame = frame[:, left : left + content_width]
    elif source_ratio < target_ratio:
        content_height = max(1, round(width / target_ratio))
        top = (height - content_height) // 2
        frame = frame[top : top + content_height, :]

    if frame.shape[1] == target_width and frame.shape[0] == target_height:
        return frame
    # Nearest-neighbor preserves the exact UI/minimap colors used by the detectors.
    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)


class FrameSource:
    """Read the newest OBS frame in a background thread without queueing old frames."""

    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        device: str = VCAM_DEVICE,
        target_size: tuple[int, int] | None = None,
    ):
        self.ffmpeg_path = resolve_ffmpeg(ffmpeg_path)
        self.device = device
        self.target_size = target_size

        self._proc: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._condition = threading.Condition()
        self._latest_frame: np.ndarray | None = None
        self._latest_wall_time = 0.0
        self._latest_monotonic = 0.0
        self._frame_count = 0
        self._running = False
        self._started_at = 0.0

    @property
    def is_running(self) -> bool:
        return self._running and self._proc is not None and self._proc.poll() is None

    @property
    def frame_count(self) -> int:
        with self._condition:
            return self._frame_count

    def __enter__(self) -> "FrameSource":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.stop()

    def _build_command(self) -> list[str]:
        return [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostats",
            "-nostdin",
            "-f",
            "dshow",
            "-i",
            f"video={self.device}",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"scale={VCAM_WIDTH}:{VCAM_HEIGHT}:flags=neighbor",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "pipe:1",
        ]

    def _reader_loop(self) -> None:
        frame_bytes = VCAM_WIDTH * VCAM_HEIGHT * 3
        assert self._proc is not None and self._proc.stdout is not None
        stream = self._proc.stdout
        while self._running and self._proc.poll() is None:
            raw = stream.read(frame_bytes)
            if not raw or len(raw) != frame_bytes:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(VCAM_HEIGHT, VCAM_WIDTH, 3)
            with self._condition:
                self._latest_frame = frame
                self._latest_wall_time = time.time()
                self._latest_monotonic = time.monotonic()
                self._frame_count += 1
                self._condition.notify_all()

        with self._condition:
            self._running = False
            self._condition.notify_all()

    def start(self, timeout: float = 5.0) -> None:
        if self.is_running:
            return

        with self._condition:
            self._latest_frame = None
            self._latest_wall_time = 0.0
            self._latest_monotonic = 0.0
            self._frame_count = 0
            self._started_at = time.monotonic()
            self._running = True

        self._proc = subprocess.Popen(
            self._build_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=VCAM_WIDTH * VCAM_HEIGHT * 3 * 2,
        )
        self._thread = threading.Thread(target=self._reader_loop, daemon=True, name="obs-frame-source")
        self._thread.start()

        deadline = time.monotonic() + timeout
        with self._condition:
            while self._latest_frame is None and self._running and time.monotonic() < deadline:
                self._condition.wait(timeout=min(0.1, deadline - time.monotonic()))
            if self._latest_frame is not None:
                return

        process = self._proc
        self.stop()
        details = ""
        if process is not None and process.stderr is not None:
            try:
                details = process.stderr.read().decode("utf-8", "replace").strip()
            except (OSError, ValueError):
                pass
        suffix = f": {details}" if details else ""
        raise TimeoutError(
            f"Nenhum frame recebido de '{self.device}' em {timeout:.1f}s. "
            f"A Camera Virtual do OBS esta iniciada?{suffix}"
        )

    def stop(self) -> None:
        with self._condition:
            self._running = False
            self._condition.notify_all()
        process = self._proc
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        if process is not None and process.poll() is None:
            raise RuntimeError(f"FFmpeg PID {process.pid} nao encerrou; handoff da camera abortado")
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Thread de captura do OBS nao encerrou; handoff da camera abortado")
        self._thread = None
        self._proc = None

    def _snapshot(self, wait_for_new: bool, timeout: float) -> tuple[np.ndarray, int, float, float]:
        deadline = time.monotonic() + timeout
        with self._condition:
            previous_count = self._frame_count if wait_for_new else -1
            while (
                self._latest_frame is None or self._frame_count <= previous_count
            ) and self._running and time.monotonic() < deadline:
                self._condition.wait(timeout=min(0.05, deadline - time.monotonic()))
            if self._latest_frame is None:
                raise RuntimeError("Nenhum frame disponivel da Camera Virtual do OBS")
            if wait_for_new and self._frame_count <= previous_count:
                raise TimeoutError(f"O stream do OBS nao entregou um frame novo em {timeout:.1f}s")
            return (
                self._latest_frame.copy(),
                self._frame_count,
                self._latest_wall_time,
                self._latest_monotonic,
            )

    def grab(self, wait_for_new: bool = False, timeout: float = 1.0) -> np.ndarray:
        frame, _sequence, _wall_time, _monotonic = self._snapshot(wait_for_new, timeout)
        return fit_frame_to_size(frame, self.target_size)

    def grab_pil(self, wait_for_new: bool = False, timeout: float = 1.0) -> Image.Image:
        frame = self.grab(wait_for_new=wait_for_new, timeout=timeout)
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def grab_to_disk(
        self,
        folder: Path,
        wait_for_new: bool = True,
        timeout: float = 1.0,
    ) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        frame, sequence, wall_time, _monotonic = self._snapshot(wait_for_new, timeout)
        frame = fit_frame_to_size(frame, self.target_size)
        path = folder / f"obs_{int(wall_time * 1000)}_{sequence:06d}.png"
        if not cv2.imwrite(str(path), frame):
            raise OSError(f"Nao foi possivel salvar o frame do OBS: {path}")

        from runtime.capture_store import prune_pngs

        prune_pngs(folder)
        return path

    def stats(self) -> dict:
        now = time.monotonic()
        with self._condition:
            elapsed = max(0.0, now - self._started_at)
            age = None if not self._latest_monotonic else max(0.0, now - self._latest_monotonic)
            return {
                "running": self.is_running,
                "frame_count": self._frame_count,
                "fps": round(self._frame_count / elapsed, 1) if elapsed else 0.0,
                "latest_age_ms": None if age is None else round(age * 1000, 1),
                "device": self.device,
                "stream_size": [VCAM_WIDTH, VCAM_HEIGHT],
                "output_size": None if self.target_size is None else list(self.target_size),
            }


class CaptureSession:
    """Own one capture backend and transparently fall back in auto mode."""

    def __init__(
        self,
        mode: str = "auto",
        ffmpeg_path: str | Path | None = None,
        device: str = VCAM_DEVICE,
        target_size: tuple[int, int] | None = None,
    ):
        if mode not in CAPTURE_MODES:
            raise ValueError(f"Fonte de captura invalida: {mode}")
        self.requested_mode = mode
        self.ffmpeg_path = ffmpeg_path
        self.device = device
        self.target_size = target_size
        self.active_mode = "stopped"
        self.fallback_reason: str | None = None
        self.stream: FrameSource | None = None
        self.chat_off_confirmed = False

    @classmethod
    def for_window(
        cls,
        hwnd: int,
        mode: str = "auto",
        ffmpeg_path: str | Path | None = None,
        device: str = VCAM_DEVICE,
    ) -> "CaptureSession":
        return cls(mode, ffmpeg_path, device, client_size(hwnd))

    @property
    def uses_obs(self) -> bool:
        return self.active_mode == "obs"

    def __enter__(self) -> "CaptureSession":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.stop()

    def start(self) -> None:
        if self.active_mode == "obs" and self.stream is not None and self.stream.is_running:
            return
        if self.requested_mode == "screenshot" or self.fallback_reason is not None:
            self.active_mode = "screenshot"
            return

        try:
            stream = FrameSource(
                ffmpeg_path=self.ffmpeg_path,
                device=self.device,
                target_size=self.target_size,
            )
            stream.start()
            self.stream = stream
            self.active_mode = "obs"
        except Exception as exc:
            if self.requested_mode == "obs":
                raise
            self.fallback(f"{type(exc).__name__}: {exc}")

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream = None
        self.active_mode = "stopped"

    def fallback(self, reason: str) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream = None
        if self.requested_mode == "obs":
            self.active_mode = "stopped"
            raise RuntimeError(f"Frame do OBS rejeitado: {reason}")
        self.fallback_reason = reason
        self.active_mode = "screenshot"

    def capture(self, hwnd: int, source_folder: Path, output_folder: Path) -> Path:
        if self.active_mode == "stopped":
            self.start()
        if self.active_mode == "obs":
            assert self.stream is not None
            try:
                return self.stream.grab_to_disk(output_folder, wait_for_new=True)
            except Exception as exc:
                if self.requested_mode == "obs":
                    raise
                self.fallback(f"{type(exc).__name__}: {exc}")

        from capture_internal import trigger_screenshot_with_retry
        from runtime.capture_store import store_generated_screenshot

        source = trigger_screenshot_with_retry(hwnd, source_folder)
        image = store_generated_screenshot(source, output_folder)
        self.chat_off_confirmed = True
        return image

    def capture_and_analyze(
        self,
        hwnd: int,
        source_folder: Path,
        output_folder: Path,
        analyzer: Callable[[Path], T],
        stream_attempts: int = 2,
    ) -> tuple[Path, T]:
        if self.active_mode == "stopped":
            self.start()
        failures = []
        attempts = stream_attempts if self.active_mode == "obs" else 1
        for _attempt in range(max(1, attempts)):
            image = self.capture(hwnd, source_folder, output_folder)
            try:
                return image, analyzer(image)
            except Exception as exc:
                if self.active_mode != "obs":
                    raise
                failures.append(f"{type(exc).__name__}: {exc}")

        reason = "; ".join(failures)
        self.fallback(reason)
        image = self.capture(hwnd, source_folder, output_folder)
        return image, analyzer(image)

    def stats(self) -> dict:
        result = {
            "requested": self.requested_mode,
            "active": self.active_mode,
            "fallback_reason": self.fallback_reason,
        }
        if self.stream is not None:
            result["stream"] = self.stream.stats()
        return result


def grab_single_frame(
    ffmpeg_path: str | Path | None = None,
    device: str = VCAM_DEVICE,
) -> tuple[np.ndarray, dict]:
    """Grab one current OBS frame using the same synchronized source."""
    with FrameSource(ffmpeg_path=ffmpeg_path, device=device) as source:
        frame = source.grab(wait_for_new=True)
        return frame, source.stats()
