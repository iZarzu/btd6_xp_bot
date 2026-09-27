"""Grabbing frames of the game.

PL: Pobieranie klatek (zrzutów) z gry.

Backends / Tryby:
  window - PrintWindow API: works while the game is COVERED by other windows
           (but NOT minimized). Windows only.
           PL: działa, gdy gra jest ZASŁONIĘTA innymi oknami (ale NIE zminimalizowana).
  screen - plain screenshot of the screen area: the game must be visible.
           PL: zwykły zrzut ekranu - gra musi być widoczna.
  auto   - window, falling back to screen if it returns black frames.
           PL: window, a gdy zwraca czarny obraz - screen.
"""
from __future__ import annotations

import ctypes
import logging

import numpy as np

from .window import IS_WINDOWS, GameWindow, open_mss

log = logging.getLogger("btd6bot")

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2  # needed for DirectX/Unity content / PL: potrzebne dla gier DirectX/Unity


class ScreenCapture:
    name = "screen"

    def __init__(self, game: GameWindow):
        self.game = game
        self._sct = None  # created lazily in the thread that uses it / PL: tworzone leniwie

    def grab(self) -> np.ndarray | None:
        if self._sct is None:
            self._sct = open_mss()
        r = self.game.rect
        shot = np.array(self._sct.grab({"left": r.left, "top": r.top, "width": r.width, "height": r.height}))
        return shot[:, :, :3]  # BGRA -> BGR


class WindowCapture:
    name = "window"

    def __init__(self, game: GameWindow):
        if not IS_WINDOWS or game.hwnd is None:
            raise RuntimeError("Window capture needs Windows and a found game window")
        self.game = game
        self._setup_winapi()

    @staticmethod
    def _setup_winapi() -> None:
        # Explicit signatures, otherwise 64-bit handles get truncated.
        # PL: Jawne sygnatury, inaczej 64-bitowe uchwyty zostaną obcięte.
        from ctypes import wintypes as w

        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        u.GetDC.argtypes = [w.HWND]
        u.GetDC.restype = w.HDC
        u.ReleaseDC.argtypes = [w.HWND, w.HDC]
        u.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
        g.CreateCompatibleDC.argtypes = [w.HDC]
        g.CreateCompatibleDC.restype = w.HDC
        g.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]
        g.CreateCompatibleBitmap.restype = w.HBITMAP
        g.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
        g.SelectObject.restype = w.HGDIOBJ
        g.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]
        g.DeleteObject.argtypes = [w.HGDIOBJ]
        g.DeleteDC.argtypes = [w.HDC]

    def grab(self) -> np.ndarray | None:
        from ctypes import wintypes as w

        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        if self.game.is_minimized:
            return None  # a minimized window is not rendered / PL: zminimalizowane okno nie jest rysowane
        hwnd = self.game.hwnd
        width, height = self.game.rect.width, self.game.rect.height

        window_dc = u.GetDC(hwnd)
        mem_dc = g.CreateCompatibleDC(window_dc)
        bitmap = g.CreateCompatibleBitmap(window_dc, width, height)
        old = g.SelectObject(mem_dc, bitmap)
        try:
            u.PrintWindow(hwnd, mem_dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                            ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                            ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                            ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]

            header = BITMAPINFOHEADER()
            header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            header.biWidth = width
            header.biHeight = -height  # negative = top-down rows / PL: ujemna = wiersze od góry
            header.biPlanes = 1
            header.biBitCount = 32
            buffer = np.empty((height, width, 4), dtype=np.uint8)
            g.GetDIBits(mem_dc, bitmap, 0, height, buffer.ctypes.data, ctypes.byref(header), 0)
        finally:
            g.SelectObject(mem_dc, old)
            g.DeleteObject(bitmap)
            g.DeleteDC(mem_dc)
            u.ReleaseDC(hwnd, window_dc)
        return buffer[:, :, :3]


class AutoCapture:
    """Prefer background capture, fall back to the screen if it only yields black frames.

    PL: Preferuj przechwytywanie w tle; jeśli daje tylko czarne klatki - przełącz na ekran.
    """

    def __init__(self, game: GameWindow):
        self.screen = ScreenCapture(game)
        try:
            self.window: WindowCapture | None = WindowCapture(game)
        except RuntimeError:
            self.window = None
        self._black_frames = 0

    @property
    def name(self) -> str:
        return "auto(window)" if self.window else "auto(screen)"

    def grab(self) -> np.ndarray | None:
        if self.window is not None:
            frame = self.window.grab()
            if frame is None:
                # Minimized: a screenshot would show some other app. / PL: Zminimalizowana - nie ma czego łapać.
                log.warning("Game window is minimized - restore it (it may stay behind other windows). "
                            "/ Okno gry jest zminimalizowane - przywróć je (może być pod innymi oknami).")
                return None
            if frame.max() > 10:
                self._black_frames = 0
                return frame
            self._black_frames += 1
            if self._black_frames >= 5:
                log.warning("Background capture returns black frames - switching to screen capture "
                            "(keep the game visible). / Przechwytywanie w tle nie działa - przełączam na ekran.")
                self.window = None
        return self.screen.grab()


def make_capture(mode: str, game: GameWindow):
    if mode == "screen":
        return ScreenCapture(game)
    if mode == "window":
        return WindowCapture(game)
    return AutoCapture(game)
