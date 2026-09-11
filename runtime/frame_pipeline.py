"""Run independent visual readers concurrently against one immutable frame."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from movement.world_model import analyze_world, localize_in_reference
from read_battle_list import read_battle_list
from read_status_bars import read_status_fast


class FramePipeline:
    def __init__(self, reference: dict, workers: int = 3):
        self.reference = reference
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tibia-reader")

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> "FramePipeline":
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def analyze(self, image_path: Path) -> tuple[dict, dict]:
        started = time.perf_counter()
        futures = {
            "battle": self.executor.submit(read_battle_list, image_path),
            "status": self.executor.submit(read_status_fast, image_path),
            "world": self.executor.submit(analyze_world, image_path, "Rafaelkrosa", False),
        }
        results = {name: future.result() for name, future in futures.items()}
        localization = localize_in_reference(results["world"], self.reference)
        battle = results["battle"]
        status = results["status"]
        snapshot = {
            "frame_id": image_path.stem,
            "image": str(image_path.resolve()),
            "captured_at_ns": image_path.stat().st_mtime_ns,
            "position": localization.get("coordinate"),
            "localized": localization["localized"],
            "agreement": localization.get("best", {}).get("agreement"),
            "matching_tiles": localization.get("best", {}).get("matching_tiles"),
            "battle_empty": battle["empty"],
            "enemies": [enemy["name"] for enemy in battle["matched_enemies"]],
            "health_percent": status["health_percent"],
            "mana_percent": status["mana_percent"],
            "analysis_seconds": round(time.perf_counter() - started, 3),
            "readers": ["battle", "status", "world"],
        }
        return snapshot, results["world"]
