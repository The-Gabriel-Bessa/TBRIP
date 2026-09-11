"""Detect activity only in the Tibia process audio session."""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from ctypes import wintypes
from pathlib import Path

from pycaw.pycaw import AudioUtilities, IAudioMeterInformation


user32 = ctypes.windll.user32


def find_tibia_window(title_fragment: str) -> tuple[int, int, str]:
    matches: list[tuple[int, int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_fragment.casefold() not in buffer.value.casefold():
            return True
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        matches.append((hwnd, process_id.value, buffer.value))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    if not matches:
        raise RuntimeError(f'Nenhuma janela contendo "{title_fragment}" foi encontrada')
    return matches[0]


def get_process_meter(process_id: int):
    sessions = AudioUtilities.GetAllSessions()
    session = next((item for item in sessions if item.ProcessId == process_id), None)
    if session is None:
        raise RuntimeError(f"O PID {process_id} nao possui uma sessao de audio")
    return session._ctl.QueryInterface(IAudioMeterInformation)


def emit(event: str, **values) -> None:
    print(
        json.dumps(
            {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **values},
            ensure_ascii=False,
        ),
        flush=True,
    )


def monitor(
    process_id: int,
    title: str,
    threshold: float,
    silence_seconds: float,
    sample_interval: float,
    duration: float,
    capture_marker: Path,
) -> None:
    meter = get_process_meter(process_id)
    started = time.monotonic()
    last_sound: float | None = None
    combat_active = False
    ignored_until = 0.0
    marker_was_present = False
    peak_max = 0.0

    emit(
        "monitor_started",
        pid=process_id,
        process="client.exe",
        window=title,
        threshold=threshold,
        silence_seconds=silence_seconds,
    )

    while duration <= 0 or time.monotonic() - started < duration:
        now = time.monotonic()
        marker_present = capture_marker.exists()
        if marker_was_present and not marker_present:
            ignored_until = now + 0.75
        marker_was_present = marker_present

        peak = float(meter.GetPeakValue())
        peak_max = max(peak_max, peak)
        ignored = marker_present or now < ignored_until
        if ignored and last_sound is not None:
            last_sound = now
        elif peak >= threshold:
            last_sound = now
            if not combat_active:
                combat_active = True
                emit("combat_started", pid=process_id, peak=round(peak, 6))
        elif (
            combat_active
            and last_sound is not None
            and now - last_sound >= silence_seconds
        ):
            combat_active = False
            emit(
                "combat_stopped",
                pid=process_id,
                silent_for=round(now - last_sound, 3),
            )

        time.sleep(sample_interval)

    emit(
        "monitor_stopped",
        pid=process_id,
        state="combat" if combat_active else "idle",
        peak_max=round(peak_max, 6),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="Tibia -", help="Trecho do titulo da janela")
    parser.add_argument("--threshold", type=float, default=0.003)
    parser.add_argument("--silence", type=float, default=4.0)
    parser.add_argument("--interval", type=float, default=0.01)
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Duracao do teste; zero monitora ate Ctrl+C",
    )
    parser.add_argument(
        "--capture-marker",
        type=Path,
        default=Path(__file__).resolve().parent / ".capture_in_progress",
    )
    args = parser.parse_args()

    _hwnd, process_id, title = find_tibia_window(args.title)
    try:
        monitor(
            process_id=process_id,
            title=title,
            threshold=max(0.0, args.threshold),
            silence_seconds=max(0.1, args.silence),
            sample_interval=max(0.005, args.interval),
            duration=max(0.0, args.duration),
            capture_marker=args.capture_marker,
        )
    except KeyboardInterrupt:
        emit("monitor_interrupted", pid=process_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
