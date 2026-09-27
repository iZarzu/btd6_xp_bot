"""Catching the user's click in the game window - used to set tower positions.

PL: Łapanie kliknięcia użytkownika w oknie gry - służy do ustawiania pozycji wież.

The GUI switches to the game and presses the tower hotkey, the user moves the mouse and clicks.
The exact click position is saved - it is the same click the bot makes later, so there is no
guessing where a tower's hitbox is.
PL: GUI przełącza na grę i wciska skrót wieży, użytkownik najeżdża myszką i klika.
Zapisywane jest dokładne miejsce kliknięcia - to samo kliknięcie wykona potem bot, więc nie
trzeba zgadywać, gdzie jest hitbox wieży.
"""
from __future__ import annotations

import ctypes
import threading
from typing import Any, Callable

from .inputs import VK_CODES
from .window import IS_WINDOWS, GameWindow

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


def game_under_cursor(game: GameWindow, x: int, y: int) -> bool:
    """True if the screen point belongs to the game window (not a window covering it).

    PL: True, jeśli punkt ekranu należy do okna gry (a nie do okna, które je zasłania).
    """
    if not IS_WINDOWS or game.hwnd is None:
        return True
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    root = user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT
    return bool(root) and int(root) == int(game.hwnd)


class ClickCatcher:
    """Waits for ONE left click on the game window (-> on_click(rel)) or Esc (-> on_cancel).
    Callbacks run in the pynput thread.

    PL: Czeka na JEDNO kliknięcie lewym przyciskiem w oknie gry (-> on_click(rel)) albo Esc
    (-> on_cancel). Callbacki działają w wątku pynput.
    """

    def __init__(self, game: GameWindow, on_click: Callable[[tuple[float, float]], None],
                 on_cancel: Callable[[], None]):
        self.game = game
        self.on_click = on_click
        self.on_cancel = on_cancel
        self._done = threading.Event()
        self._listeners: list[Any] = []

    def start(self) -> None:
        from pynput import keyboard, mouse

        self._listeners = [mouse.Listener(on_click=self._handle_click), keyboard.Listener(on_press=self._handle_key)]
        for listener in self._listeners:
            listener.daemon = True
            listener.start()

    def stop(self) -> None:
        self._done.set()
        for listener in self._listeners:
            listener.stop()
        self._listeners = []

    def _finish(self) -> bool:
        if self._done.is_set():
            return False
        self._done.set()
        threading.Thread(target=self.stop, daemon=True).start()  # can't join a listener from itself
        return True

    def _handle_click(self, x: int, y: int, button, pressed: bool) -> None:
        if not pressed or getattr(button, "name", "") != "left" or not game_under_cursor(self.game, x, y):
            return
        self.game.refresh()
        r = self.game.rect
        rel = ((x - r.left) / r.width, (y - r.top) / r.height)
        if 0 <= rel[0] <= 1 and 0 <= rel[1] <= 1 and self._finish():
            self.on_click((round(rel[0], 4), round(rel[1], 4)))

    def _handle_key(self, key) -> None:
        if key_name(key) in ("esc", "escape") and self._finish():
            self.on_cancel()
