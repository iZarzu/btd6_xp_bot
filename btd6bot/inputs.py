"""Sending mouse clicks and key presses to the game.

PL: Wysyłanie kliknięć i klawiszy do gry.

Backends / Tryby:
  foreground - real mouse + keyboard. The game must be the active window the whole time.
               PL: prawdziwa mysz i klawiatura. Gra musi być cały czas aktywnym oknem.
  burst      - (recommended) real input, but the bot activates the game only for the few
               seconds it needs (placing towers, menus) and then gives focus and the cursor
               back to whatever you were doing. Between games you can work normally.
               PL: (zalecany) bot aktywuje grę tylko na kilka sekund, kiedy musi coś kliknąć,
               a potem oddaje Ci okno i kursor. W trakcie gry możesz normalnie pracować.
  background - EXPERIMENTAL. Window messages (PostMessage) sent straight to the game window,
               nothing on your screen moves. Some Unity games ignore these messages -
               test it in the GUI before relying on it.
               PL: EKSPERYMENTALNY. Komunikaty wysyłane prosto do okna gry, nic się nie rusza.
               Niektóre gry Unity je ignorują - przetestuj w GUI zanim na tym polegasz.
"""
from __future__ import annotations

import contextlib
import ctypes
import time

from .window import IS_WINDOWS, GameWindow

# Virtual-key codes for keys used by BTD6. / PL: Kody klawiszy używanych w BTD6.
VK_CODES = {
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08, "enter": 0x0D, "tab": 0x09,
    ",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE, "[": 0xDB, "]": 0xDD, "-": 0xBD, "=": 0xBB,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}

WM_ACTIVATE, WM_SETFOCUS = 0x0006, 0x0007
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
MK_LBUTTON = 0x0001


def vk_code(key: str) -> int:
    key = key.lower()
    if key in VK_CODES:
        return VK_CODES[key]
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    raise ValueError(f"Unknown key / nieznany klawisz: {key!r}")


class ForegroundInput:
    name = "foreground"

    def __init__(self, game: GameWindow, click_delay: float):
        self.game = game
        self.click_delay = click_delay
        import pyautogui

        pyautogui.FAILSAFE = True  # mouse to top-left corner = emergency stop / PL: awaryjny stop
        pyautogui.PAUSE = 0.03
        self._mouse = pyautogui
        try:
            # DirectInput scan codes are more reliable in games. / PL: Pewniejsze w grach.
            import pydirectinput

            pydirectinput.PAUSE = 0.03
            self._keys = pydirectinput
        except ImportError:
            self._keys = pyautogui

    @contextlib.contextmanager
    def session(self):
        """A group of inputs executed together. / PL: Grupa akcji wykonywanych razem."""
        yield

    def move(self, rel: tuple[float, float]) -> None:
        self._mouse.moveTo(*self.game.rect.to_abs(rel), duration=0.05)

    def click(self, rel: tuple[float, float]) -> None:
        self.move(rel)
        time.sleep(0.05)
        self._mouse.click()
        time.sleep(self.click_delay)

    def press(self, key: str, times: int = 1) -> None:
        for _ in range(times):
            self._keys.press(key)
            time.sleep(self.click_delay)


class BurstInput(ForegroundInput):
    name = "burst"

    def __init__(self, game: GameWindow, click_delay: float):
        if not IS_WINDOWS or game.hwnd is None:
            raise RuntimeError("Burst input needs Windows and a found game window")
        super().__init__(game, click_delay)
        self._depth = 0

    @contextlib.contextmanager
    def session(self):
        # Nested sessions reuse the outer one. / PL: Zagnieżdżone sesje używają zewnętrznej.
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        previous = user32.GetForegroundWindow()
        cursor = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(cursor))
        self._depth = 1
        try:
            _bring_to_front(self.game.hwnd)
            self.game.refresh()
            time.sleep(0.25)
            yield
        finally:
            self._depth = 0
            if previous and previous != self.game.hwnd:
                _bring_to_front(previous)
            user32.SetCursorPos(cursor.x, cursor.y)


class BackgroundInput:
    name = "background"

    def __init__(self, game: GameWindow, click_delay: float):
        if not IS_WINDOWS or game.hwnd is None:
            raise RuntimeError("Background input needs Windows and a found game window")
        self.game = game
        self.click_delay = click_delay
        self._post = ctypes.windll.user32.PostMessageW
        self._post.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        self._scan = ctypes.windll.user32.MapVirtualKeyW

    @contextlib.contextmanager
    def session(self):
        # Pretend the window is active; many games drop input otherwise.
        # PL: Udajemy, że okno jest aktywne - inaczej wiele gier ignoruje wejście.
        self._post(self.game.hwnd, WM_ACTIVATE, 1, 0)
        self._post(self.game.hwnd, WM_SETFOCUS, 0, 0)
        yield

    def _mouse_lparam(self, rel: tuple[float, float]) -> int:
        x, y = self.game.rect.to_client(rel)
        return (y << 16) | (x & 0xFFFF)

    def move(self, rel: tuple[float, float]) -> None:
        self._post(self.game.hwnd, WM_MOUSEMOVE, 0, self._mouse_lparam(rel))
        time.sleep(0.05)

    def click(self, rel: tuple[float, float]) -> None:
        lparam = self._mouse_lparam(rel)
        self._post(self.game.hwnd, WM_MOUSEMOVE, 0, lparam)
        time.sleep(0.05)
        self._post(self.game.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(0.05)
        self._post(self.game.hwnd, WM_LBUTTONUP, 0, lparam)
        time.sleep(self.click_delay)

    def press(self, key: str, times: int = 1) -> None:
        vk = vk_code(key)
        scan = self._scan(vk, 0)
        down = 1 | (scan << 16)
        up = down | (1 << 30) | (1 << 31)
        for _ in range(times):
            self._post(self.game.hwnd, WM_KEYDOWN, vk, down)
            time.sleep(0.04)
            self._post(self.game.hwnd, WM_KEYUP, vk, up)
            time.sleep(self.click_delay)


def _bring_to_front(hwnd: int) -> None:
    """SetForegroundWindow is blocked for background processes unless we attach to the
    foreground thread first (standard WinAPI workaround).

    PL: Windows blokuje SetForegroundWindow dla procesów w tle, chyba że najpierw
    podepniemy się pod wątek aktywnego okna (standardowe obejście WinAPI).
    """
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    foreground = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(foreground, None)
    this_thread = kernel32.GetCurrentThreadId()
    attached = fg_thread != this_thread and user32.AttachThreadInput(this_thread, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(this_thread, fg_thread, False)


def make_input(mode: str, game: GameWindow, click_delay: float):
    backends = {"foreground": ForegroundInput, "burst": BurstInput, "background": BackgroundInput}
    return backends[mode](game, click_delay)
