"""Locating the game window and converting between relative and absolute coordinates.

PL: Wyszukiwanie okna gry i przeliczanie współrzędnych względnych <-> bezwzględnych.

All positions in configs/strategies are RELATIVE to the game's client area (0.0-1.0),
so the same strategy works on 1080p, 1440p and 4K as long as the aspect ratio is 16:9.
PL: Wszystkie pozycje są WZGLĘDNE (0.0-1.0) względem obszaru gry, więc ta sama strategia
działa na 1080p, 1440p i 4K, o ile proporcje ekranu to 16:9.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.windll.user32


def enable_dpi_awareness() -> None:
    """Without this, Windows display scaling (e.g. 150% on 4K) breaks pixel coordinates.

    PL: Bez tego skalowanie Windows (np. 150% na 4K) psuje współrzędne pikseli.
    """
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int

    def to_abs(self, rel: tuple[float, float]) -> tuple[int, int]:
        return round(self.left + rel[0] * self.width), round(self.top + rel[1] * self.height)

    def to_client(self, rel: tuple[float, float]) -> tuple[int, int]:
        """Pixel position inside the window (used by background input). / PL: Piksel wewnątrz okna."""
        return round(rel[0] * self.width), round(rel[1] * self.height)

    def to_rel(self, abs_xy: tuple[int, int]) -> tuple[float, float]:
        return (round((abs_xy[0] - self.left) / self.width, 4),
                round((abs_xy[1] - self.top) / self.height, 4))


@dataclass
class GameWindow:
    hwnd: int | None  # None = no window handle, we use a whole monitor / PL: brak okna, cały monitor
    rect: Rect

    def refresh(self) -> None:
        """The window may be moved or resized between games. / PL: Okno mogło zostać przesunięte."""
        if self.hwnd is not None:
            rect = client_rect(self.hwnd)
            if rect:
                self.rect = rect

    @property
    def is_minimized(self) -> bool:
        return bool(self.hwnd and IS_WINDOWS and user32.IsIconic(self.hwnd))


def find_window(title: str) -> int | None:
    """Return the handle of the first visible window whose title contains `title`.

    PL: Zwraca uchwyt pierwszego widocznego okna, którego tytuł zawiera `title`.
    """
    if not IS_WINDOWS or not title:
        return None
    found: list[int] = []
    needle = title.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if needle in buf.value.lower():
                    found.append(hwnd)
                    return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def client_rect(hwnd: int) -> Rect | None:
    """Screen rectangle of the window content, without borders and title bar.

    PL: Prostokąt zawartości okna na ekranie, bez ramki i paska tytułu.
    """
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or rect.right <= 0 or rect.bottom <= 0:
        return None
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return Rect(origin.x, origin.y, rect.right, rect.bottom)


def locate_game(title: str, monitor: int = 1) -> GameWindow:
    """Find the game window; fall back to a whole monitor (non-Windows or window not found).

    PL: Znajdź okno gry; jeśli się nie da - użyj całego monitora.
    """
    hwnd = find_window(title)
    if hwnd:
        rect = client_rect(hwnd)
        if rect:
            return GameWindow(hwnd, rect)
    with open_mss() as sct:
        m = sct.monitors[min(monitor, len(sct.monitors) - 1)]
        return GameWindow(None, Rect(m["left"], m["top"], m["width"], m["height"]))


def open_mss():
    """mss >= 10 renamed `mss.mss` to `mss.MSS`. / PL: Nowsze mss zmieniło nazwę klasy."""
    import mss

    factory = getattr(mss, "MSS", None) or mss.mss
    return factory()
