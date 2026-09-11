"""Trigger Tibia's built-in screenshot and copy it into this project."""

from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import time
from ctypes import wintypes
from pathlib import Path


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
VK_RETURN = 0x0D
VK_MULTIPLY = 0x6A
KEYEVENTF_KEYUP = 0x0002


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
    prefix_matches = [match for match in matches if match[1].casefold().startswith(title_fragment.casefold())]
    if prefix_matches:
        matches = prefix_matches
    if len(matches) > 1:
        titles = ", ".join(repr(title) for _hwnd, title in matches)
        raise RuntimeError(f'Mais de uma janela corresponde a "{title_fragment}": {titles}')
    return matches[0]


def focus_window(hwnd: int, timeout: float = 1.0) -> None:
    """Focus the expected window and fail closed if Windows refuses the switch."""
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        raise RuntimeError("A janela do Tibia nao esta mais disponivel")
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached_threads = []
    for thread_id in {target_thread, foreground_thread} - {0, current_thread}:
        if user32.AttachThreadInput(current_thread, thread_id, True):
            attached_threads.append(thread_id)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        for thread_id in attached_threads:
            user32.AttachThreadInput(current_thread, thread_id, False)
    deadline = time.monotonic() + timeout
    while user32.GetForegroundWindow() != hwnd and time.monotonic() < deadline:
        time.sleep(0.02)
    if user32.GetForegroundWindow() != hwnd:
        raise RuntimeError("Nao foi possivel confirmar o foco na janela do Tibia")


def press_key(virtual_key: int, hwnd: int | None = None) -> None:
    if hwnd is not None:
        focus_window(hwnd)
    try:
        user32.keybd_event(virtual_key, 0, 0, 0)
    finally:
        user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)


def newest_png(folder: Path) -> Path | None:
    files = list(folder.glob("*.png"))
    return max(files, key=lambda path: path.stat().st_mtime_ns) if files else None


def wait_for_new_png(folder: Path, previous: set[Path], timeout: float) -> Path | None:
    deadline = time.monotonic() + timeout
    last_signature: tuple[tuple[str, int], ...] = ()
    last_change = time.monotonic()
    latest_new_files: set[Path] = set()
    while time.monotonic() < deadline:
        new_files = {
            path
            for path in set(folder.glob("*.png")) - previous
            if "_Hotkey" in path.name
        }
        latest_new_files = new_files
        signature = tuple(sorted((path.name, path.stat().st_size) for path in new_files))
        if signature != last_signature:
            last_signature = signature
            last_change = time.monotonic()
        elif new_files and time.monotonic() - last_change >= 0.5:
            return max(new_files, key=lambda path: path.name)
        time.sleep(0.1)
    return max(latest_new_files, key=lambda path: path.name) if latest_new_files else None


def trigger_screenshot(hwnd: int, screenshot_folder: Path) -> Path:
    previous_files = set(screenshot_folder.glob("*.png"))
    foreground_before = user32.GetForegroundWindow()
    capture_marker = Path(__file__).resolve().parent / ".capture_in_progress"

    try:
        capture_marker.write_text(str(time.time()), encoding="ascii")
        focus_window(hwnd)
        time.sleep(0.8)

        # If Chat is already On, capture directly and normalize back to Chat Off.
        press_key(VK_MULTIPLY, hwnd)
        result = wait_for_new_png(screenshot_folder, previous_files, 2.5)
        if result is not None:
            press_key(VK_RETURN, hwnd)
            return result

        # Otherwise Enter enables Chat, and the second Enter returns to combat mode.
        press_key(VK_RETURN, hwnd)
        time.sleep(0.3)
        try:
            press_key(VK_MULTIPLY, hwnd)
            result = wait_for_new_png(screenshot_folder, previous_files, 8.0)
        finally:
            press_key(VK_RETURN, hwnd)
        if result is None:
            raise TimeoutError("O Tibia nao criou um screenshot novo")
        return result
    finally:
        capture_marker.unlink(missing_ok=True)
        if foreground_before and foreground_before != hwnd:
            user32.SwitchToThisWindow(foreground_before, True)


def trigger_screenshot_with_retry(
    hwnd: int,
    screenshot_folder: Path,
    attempts: int = 2,
) -> Path:
    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            return trigger_screenshot(hwnd, screenshot_folder)
        except TimeoutError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5)
    assert last_error is not None
    raise last_error


def screenshot_scope(config_path: Path) -> str:
    try:
        options = json.loads(config_path.read_text(encoding="utf-8"))
        game_options = options.get("options", {})
        only_game = game_options.get("screnshotsOnlyGameWindow")
        if only_game is True:
            return "game_window_only"
        if only_game is False:
            return "whole_client_interface"
    except (OSError, ValueError):
        pass
    return "unknown"


def main() -> int:
    local_app_data = Path.home() / "AppData" / "Local"
    tibia_data = local_app_data / "Tibia" / "packages" / "Tibia"

    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="Tibia -", help="Trecho do titulo da janela")
    parser.add_argument(
        "--source",
        type=Path,
        default=tibia_data / "screenshots",
        help="Pasta de screenshots do Tibia",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "internal_captures",
        help="Pasta que recebera a copia",
    )
    args = parser.parse_args()

    if not args.source.is_dir():
        raise RuntimeError(f"Pasta de origem nao encontrada: {args.source}")
    args.output.mkdir(parents=True, exist_ok=True)

    hwnd, title = find_window(args.title)
    source = trigger_screenshot_with_retry(hwnd, args.source)
    destination = args.output / source.name
    shutil.copy2(source, destination)

    result = {
        "window": title,
        "source": str(source),
        "saved": str(destination.resolve()),
        "scope": screenshot_scope(tibia_data / "conf" / "clientoptions.json"),
    }
    try:
        from read_status_bars import read_status

        result["status"] = read_status(destination)
    except Exception as exc:
        result["status_error"] = f"{type(exc).__name__}: {exc}"
    try:
        from read_battle_list import read_battle_list

        result["battle_list"] = read_battle_list(destination)
    except Exception as exc:
        result["battle_list_error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
