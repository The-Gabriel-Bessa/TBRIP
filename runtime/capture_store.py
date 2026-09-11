"""Store bot-generated screenshots in a bounded rolling buffer."""

from __future__ import annotations

import shutil
from pathlib import Path


def prune_pngs(folder: Path, keep: int = 100) -> int:
    files = sorted(folder.glob("*.png"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    removed = 0
    for path in files[max(1, keep) :]:
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def store_generated_screenshot(source: Path, output_folder: Path, keep: int = 100) -> Path:
    output_folder.mkdir(parents=True, exist_ok=True)
    destination = output_folder / source.name
    shutil.copy2(source, destination)
    source.unlink(missing_ok=True)
    prune_pngs(output_folder, keep)
    return destination
