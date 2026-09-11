"""Serialize client actions and apply the bot's global priority rules."""

from __future__ import annotations

import threading
from contextlib import contextmanager


class ActionCoordinator:
    def __init__(self, heal_below: float = 70.0):
        self.heal_below = heal_below
        self._action_lock = threading.Lock()
        self.active_action: str | None = None
        self.frame_id: str | None = None

    def decide(self, snapshot: dict, loot_pending: bool = False, movement_ready: bool = True) -> str:
        if snapshot["health_percent"] < self.heal_below:
            return "heal"
        if not snapshot["battle_empty"]:
            return "combat"
        if loot_pending:
            return "loot"
        if movement_ready:
            return "move"
        return "idle"

    @contextmanager
    def action(self, name: str, frame_id: str):
        with self._action_lock:
            self.active_action = name
            self.frame_id = frame_id
            try:
                yield
            finally:
                self.active_action = None
                self.frame_id = None
