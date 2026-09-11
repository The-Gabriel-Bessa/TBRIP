"""Insta-ataque reativo a som: clicou som, clica no 1o slot da Battle List.

Motivo: o loop normal de combate (screenshot + OCR da battle list) leva
2-4s por scan. Todo inimigo que ataca gera som no processo do Tibia, entao
usamos o AudioTracker como gatilho para clicar IMEDIATAMENTE no primeiro
slot da Battle List + tecla de ataque, sem esperar OCR.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from pathlib import Path


user32 = ctypes.windll.user32
VK_P = 0x50
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Posicao relativa do 1o slot da Battle List dentro da area cliente.
# Calibrado a partir de captura 1280px: entry "Amazon" em ~x=0.905, y=0.605.
BATTLE_FIRST_REL_X = 0.905
BATTLE_FIRST_REL_Y = 0.605
BATTLE_FIRST_Y_OFFSET = 16  # Ajuste fino: desce 16px na tela


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def battle_first_slot_screen_point(hwnd: int) -> tuple[int, int]:
    client = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise ctypes.WinError()
    client_width = client.right - client.left
    client_height = client.bottom - client.top
    client_x = int(client_width * BATTLE_FIRST_REL_X)
    client_y = int(client_height * BATTLE_FIRST_REL_Y) + BATTLE_FIRST_Y_OFFSET
    point_type = wintypes.POINT(client_x, client_y)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point_type)):
        raise ctypes.WinError()
    return point_type.x, point_type.y


def click_battle_first_slot(hwnd: int, press_attack: bool = True) -> dict:
    """Clica no 1o slot da Battle List e aperta P. Nao faz screenshot/OCR."""
    from capture_internal import press_key

    screen_x, screen_y = battle_first_slot_screen_point(hwnd)
    user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.05)
    user32.SetCursorPos(screen_x, screen_y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.08)
    if press_attack:
        press_key(VK_P)
    return {"screen_click": [screen_x, screen_y], "key": "P" if press_attack else None}


class FastAttackGuard(threading.Thread):
    """Thread que vigia o audio e da insta-click no 1o slot ao ouvir som.

    - poll a cada 20ms (bem mais rapido que o scan de 2-4s)
    - so dispara se silent_for <= trigger_window (som AGORA, nao ha 4s atras)
    - respeita cooldown entre cliques para nao floodar
    - pausa durante screenshot (marker) para nao roubar o mouse do fluxo
    - pode ser suspenso durante autoloot via `suspended`
    """

    def __init__(
        self,
        hwnd: int,
        audio,
        marker: Path | None = None,
        trigger_window: float = 0.35,
        cooldown: float = 1.0,
        on_attack=None,
    ):
        super().__init__(daemon=True)
        self.hwnd = hwnd
        self.audio = audio
        self.marker = marker
        self.trigger_window = trigger_window
        self.cooldown = cooldown
        self.on_attack = on_attack
        self.suspended = False
        self.stop_event = threading.Event()
        self.last_attack = 0.0
        self.fast_attacks = 0
        self._suppressed_until = 0.0
        self._battle_list_has_enemies = True  # assume true ate provar o contrario

    def set_battle_list_state(self, has_enemies: bool) -> None:
        """Chamado pelo loop principal pra informar se tem inimigos."""
        self._battle_list_has_enemies = has_enemies

    def suppress_for(self, seconds: float) -> None:
        """Suprime o guard por X segundos (apos nosso proprio ataque)."""
        self._suppressed_until = time.monotonic() + seconds

    def stop(self) -> None:
        self.stop_event.set()

    def should_fire(self) -> bool:
        if self.suspended or self.stop_event.is_set():
            return False
        if self.marker is not None and self.marker.exists():
            return False
        # Nao dispara se nao tem inimigos na battle list
        if not self._battle_list_has_enemies:
            return False
        # Nao dispara se o AudioTracker nunca detectou som acima do threshold.
        if not self.audio.ever_heard_sound:
            return False
        # Suprimido apos nosso proprio ataque
        if time.monotonic() < self._suppressed_until:
            return False
        try:
            silent = self.audio.silent_for()
        except Exception:
            return False
        if silent <= 0.0 or silent > self.trigger_window:
            return False
        now = time.monotonic()
        if now - self.last_attack < self.cooldown:
            return False
        return True

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                if self.should_fire():
                    result = click_battle_first_slot(self.hwnd, press_attack=True)
                    self.last_attack = time.monotonic()
                    self.fast_attacks += 1
                    if self.on_attack is not None:
                        try:
                            self.on_attack(result)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(0.02)
