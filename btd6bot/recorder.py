"""Recording tower positions by placing the towers once by hand.

PL: Nagrywanie pozycji wież przez jednorazowe postawienie ich ręcznie.

While recording, the user places towers in the game as usual: tower hotkey (e.g. Z) + click.
The exact click position is recorded - it is the same click the bot will make later, so there
is no guessing where a tower's hitbox is. Esc cancels a pending tower.
Only `at: [x, y]` of the existing `place` steps is updated; upgrades and everything else stay.
PL: Podczas nagrywania stawia się wieże w grze jak zwykle: skrót wieży (np. Z) + klik.
Zapisywana jest dokładna pozycja kliknięcia - to samo kliknięcie wykona potem bot, więc nie
trzeba zgadywać, gdzie jest hitbox wieży. Esc anuluje wieżę pod kursorem.
Zmieniane jest tylko `at: [x, y]` w istniejących krokach `place`; ulepszenia i reszta zostają.
"""
from __future__ import annotations

import ctypes
import logging
import re
import threading
from typing import Any, Callable

from .inputs import VK_CODES
from .window import IS_WINDOWS, GameWindow

log = logging.getLogger("btd6bot")

_VK_NAMES = {code: name for name, code in VK_CODES.items() if name != "escape"}


def key_name(key: Any) -> str | None:
    """Normalize a pynput key to our key names ('z', ',', 'esc'...). / PL: Nazwa klawisza jak w configu."""
    name = getattr(key, "name", None)  # special keys: Key.esc, Key.space...
    if name:
        return name
    char = getattr(key, "char", None)
    if char and char.isprintable():
        return char.lower()
    vk = getattr(key, "vk", None)  # e.g. char is None while a modifier is held / PL: np. z wciśniętym Ctrl
    if vk is not None:
        if vk in _VK_NAMES:
            return _VK_NAMES[vk]
        if 0x30 <= vk <= 0x5A:
            return chr(vk).lower()
    return None


class PositionRecorder:
    """Pure recording logic, fed with normalized events (easy to test).

    PL: Sama logika nagrywania, zasilana znormalizowanymi zdarzeniami (łatwa do testów).
    """

    def __init__(self, towers: dict[str, str]):
        self.key_to_tower = {str(k).lower(): t for t, k in towers.items()}
        self.placements: list[tuple[str, tuple[float, float]]] = []
        self.pending: str | None = None

    def on_key(self, key: str) -> None:
        if key in ("esc", "escape"):
            self.pending = None
        elif key in self.key_to_tower:
            self.pending = self.key_to_tower[key]

    def on_click(self, rel: tuple[float, float]) -> None:
        if not self.pending:
            return  # a normal click (selecting, menus) / PL: zwykły klik (zaznaczanie, menu)
        pos = (round(rel[0], 4), round(rel[1], 4))
        self.placements.append((self.pending, pos))
        log.info("Recorded: %s at %s", self.pending, list(pos))
        self.pending = None

    def undo(self) -> None:
        if self.placements:
            self.placements.pop()
        self.pending = None


class LiveRecorder:
    """Connects PositionRecorder to the real mouse and keyboard (pynput). Only input aimed at
    the game window is recorded, so clicks and typing in other windows are ignored.

    PL: Łączy PositionRecorder z prawdziwą myszą i klawiaturą (pynput). Nagrywane jest tylko
    wejście skierowane do okna gry, więc kliknięcia i pisanie w innych oknach są ignorowane.
    """

    def __init__(self, recorder: PositionRecorder, game: GameWindow, on_change: Callable[[], None]):
        self.recorder = recorder
        self.game = game
        self.on_change = on_change
        self.lock = threading.Lock()
        self._listeners: list[Any] = []

    def start(self) -> None:
        from pynput import keyboard, mouse

        self._listeners = [keyboard.Listener(on_press=self._on_press), mouse.Listener(on_click=self._on_click)]
        for listener in self._listeners:
            listener.daemon = True
            listener.start()

    def stop(self) -> None:
        for listener in self._listeners:
            listener.stop()
        self._listeners = []

    def _on_press(self, key) -> None:
        name = key_name(key)
        if name is None or not self._game_has_focus():
            return
        with self.lock:
            self.recorder.on_key(name)
        self.on_change()

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        if not pressed or getattr(button, "name", "") != "left" or not self._game_under_cursor(x, y):
            return
        self.game.refresh()
        r = self.game.rect
        rel = ((x - r.left) / r.width, (y - r.top) / r.height)
        if not (0 <= rel[0] <= 1 and 0 <= rel[1] <= 1):
            return
        with self.lock:
            self.recorder.on_click(rel)
        self.on_change()

    def _game_has_focus(self) -> bool:
        if not IS_WINDOWS or self.game.hwnd is None:
            return True
        return ctypes.windll.user32.GetForegroundWindow() == self.game.hwnd

    def _game_under_cursor(self, x: int, y: int) -> bool:
        if not IS_WINDOWS or self.game.hwnd is None:
            return True
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        root = user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT
        return bool(root) and int(root) == int(self.game.hwnd)


_PLACE_LINE = re.compile(r"^\s*-\s*place:\s*\{.*\}")
_TOWER = re.compile(r"tower:\s*([\w-]+)")
_AT = re.compile(r"at:\s*\[[^\]]*\]")


def apply_positions(text: str, placements: list[tuple[str, tuple[float, float]]]) -> tuple[str, int, list[str]]:
    """Put recorded positions into the existing `place` lines, matched by tower type in order
    (1st recorded sniper -> 1st sniper line...). Only `at: [...]` is changed.
    Returns (new text, number of updated lines, tower types that had no matching line).

    PL: Wstawia nagrane pozycje do istniejących linii `place`, dopasowując po typie wieży
    w kolejności (1. nagrany snajper -> 1. linia snajpera...). Zmieniane jest tylko `at: [...]`.
    Zwraca (nowy tekst, liczbę zmienionych linii, typy wież bez pasującej linii).
    """
    queues: dict[str, list[tuple[float, float]]] = {}
    for tower, pos in placements:
        queues.setdefault(tower, []).append(pos)
    lines = text.splitlines(keepends=True)
    updated = 0
    for i, line in enumerate(lines):
        if not _PLACE_LINE.match(line):
            continue
        tower = _TOWER.search(line)
        if not tower or not queues.get(tower.group(1)):
            continue
        x, y = queues[tower.group(1)].pop(0)
        lines[i] = _AT.sub(f"at: [{x}, {y}]", line, count=1)
        updated += 1
    unmatched = [tower for tower, rest in queues.items() for _ in rest]
    return "".join(lines), updated, unmatched
