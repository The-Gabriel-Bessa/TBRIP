"""Compare non-invasive Windows capture methods against the Tibia window."""

from __future__ import annotations

import argparse
import ctypes
import json
import threading
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PIL import Image, ImageGrab


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2
DIB_RGB_COLORS = 0
BI_RGB = 0


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def find_window(title_fragment: str) -> tuple[int, str]:
    matches: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_fragment.casefold() in buffer.value.casefold():
            matches.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    if not matches:
        raise RuntimeError(f'Nenhuma janela contendo "{title_fragment}" foi encontrada')
    return matches[0]


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return rect.left, rect.top, rect.right, rect.bottom


def window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    if not user32.GetClassNameW(hwnd, buffer, len(buffer)):
        raise ctypes.WinError()
    return buffer.value


def display_affinity(hwnd: int) -> int | None:
    affinity = wintypes.DWORD()
    if not user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity)):
        return None
    return affinity.value


def capture_print_window(hwnd: int, flags: int) -> Image.Image:
    left, top, right, bottom = window_rect(hwnd)
    width, height = right - left, bottom - top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)

    try:
        user32.PrintWindow(hwnd, memory_dc, flags)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        pixels = ctypes.create_string_buffer(width * height * 4)
        copied = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            pixels,
            ctypes.byref(info),
            DIB_RGB_COLORS,
        )
        if copied != height:
            raise ctypes.WinError()
        return Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1).copy()
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


def capture_wgc(timeout: float = 8.0, **target) -> Image.Image:
    try:
        from windows_capture import WindowsCapture
    except ImportError as exc:
        raise RuntimeError("O pacote windows-capture nao esta instalado neste Python") from exc

    latest: list[np.ndarray | None] = [None]
    frame_count = [0]
    ready = threading.Event()
    capture = WindowsCapture(cursor_capture=False, **target)

    @capture.event
    def on_frame_arrived(frame, _capture_control):
        latest[0] = np.array(frame.frame_buffer, copy=True)
        frame_count[0] += 1
        if frame_count[0] >= 5:
            ready.set()

    @capture.event
    def on_closed():
        ready.set()

    control = capture.start_free_threaded()
    try:
        if not ready.wait(timeout):
            raise TimeoutError(f"WGC nao entregou frames em {timeout:.0f}s")
    finally:
        control.stop()

    frame = latest[0]
    if frame is None:
        raise RuntimeError("A sessao WGC encerrou sem entregar imagem")
    if frame.shape[2] == 4:
        frame = frame[:, :, :3]
    return Image.fromarray(frame[:, :, ::-1])


def image_metrics(image: Image.Image) -> dict[str, float | int | list[int]]:
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    near_black = np.all(pixels <= 5, axis=2)
    luminance = (
        pixels[:, :, 0].astype(np.float32) * 0.2126
        + pixels[:, :, 1].astype(np.float32) * 0.7152
        + pixels[:, :, 2].astype(np.float32) * 0.0722
    )
    return {
        "size": [image.width, image.height],
        "mean_luminance": round(float(luminance.mean()), 3),
        "std_luminance": round(float(luminance.std()), 3),
        "near_black_percent": round(float(near_black.mean() * 100), 3),
        "non_black_pixels": int((~near_black).sum()),
    }


def save_result(name: str, image: Image.Image, output: Path, report: dict) -> None:
    path = output / f"{name}.png"
    image.save(path)
    report["captures"][name] = {"path": str(path), **image_metrics(image)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="Tibia -", help="Trecho do titulo da janela")
    parser.add_argument("--output", default="captures", help="Diretorio de saida")
    parser.add_argument(
        "--focus",
        action="store_true",
        help="Traz a janela ao primeiro plano durante o teste e restaura a anterior",
    )
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    hwnd, title = find_window(args.title)
    rect = window_rect(hwnd)
    foreground_before = user32.GetForegroundWindow()
    if args.focus and foreground_before != hwnd:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.SwitchToThisWindow(hwnd, True)
        time.sleep(1.0)
    report: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "window": {
            "hwnd": hwnd,
            "title": title,
            "class": window_class(hwnd),
            "rect": list(rect),
            "minimized": bool(user32.IsIconic(hwnd)),
            "foreground": user32.GetForegroundWindow() == hwnd,
            "display_affinity": display_affinity(hwnd),
        },
        "captures": {},
        "errors": {},
    }

    def capture_wgc_monitor_crop() -> Image.Image:
        monitor = capture_wgc(monitor_index=1)
        return monitor.crop(rect)

    methods = {
        "desktop_crop": lambda: ImageGrab.grab(bbox=rect, all_screens=True),
        "printwindow_default": lambda: capture_print_window(hwnd, 0),
        "printwindow_full": lambda: capture_print_window(hwnd, PW_RENDERFULLCONTENT),
        "printwindow_client_full": lambda: capture_print_window(
            hwnd, PW_CLIENTONLY | PW_RENDERFULLCONTENT
        ),
        "wgc_window_hwnd": lambda: capture_wgc(window_hwnd=hwnd),
        "wgc_window_name": lambda: capture_wgc(window_name=title),
        "wgc_monitor_crop": capture_wgc_monitor_crop,
    }
    try:
        for name, method in methods.items():
            try:
                save_result(name, method(), output, report)
            except Exception as exc:
                report["errors"][name] = f"{type(exc).__name__}: {exc}"
    finally:
        if args.focus and foreground_before and foreground_before != hwnd:
            user32.SwitchToThisWindow(foreground_before, True)

    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["captures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
