"""Serialize client actions and apply the bot's global priority rules."""

from __future__ import annotations

import threading
from contextlib import contextmanager


def resource_action(
    snapshot: dict,
    heal_below: float = 90.0,
    emergency_hp: int = 300,
) -> str | None:
    health = snapshot.get("health") or {}
    health_current = snapshot.get("health_current", health.get("current"))
    if health_current is not None and health_current < emergency_hp:
        return "emergency_heal"
    if snapshot["health_percent"] < heal_below:
        return "heal"
    return None


class ActionCoordinator:
    def __init__(
        self,
        heal_below: float = 90.0,
        emergency_hp: int = 300,
    ):
        self.heal_below = heal_below
        self.emergency_hp = emergency_hp
        self._action_lock = threading.Lock()
        self.active_action: str | None = None
        self.frame_id: str | None = None

    def decide(self, snapshot: dict, loot_pending: bool = False, movement_ready: bool = True) -> str:
        resource = resource_action(
            snapshot,
            heal_below=self.heal_below,
            emergency_hp=self.emergency_hp,
        )
        if resource is not None:
            return resource
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
