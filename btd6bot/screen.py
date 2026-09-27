"""Zrzuty ekranu, przeliczanie współrzędnych i rozpoznawanie obrazków (template matching).

Wszystkie pozycje w konfiguracji są WZGLĘDNE (0.0-1.0) względem okna gry,
dzięki czemu strategia działa na każdej rozdzielczości 16:9.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import mss
import numpy as np


def enable_dpi_awareness() -> None:
    """Na Windowsie ze skalowaniem (np. 125%) współrzędne mss i myszy się rozjeżdżają bez tego."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class Region:
    left: int
    top: int
    width: int
    height: int

    def to_abs(self, rel: tuple[float, float]) -> tuple[int, int]:
        x, y = rel
        return round(self.left + x * self.width), round(self.top + y * self.height)

    def to_rel(self, abs_xy: tuple[int, int]) -> tuple[float, float]:
        x, y = abs_xy
        return round((x - self.left) / self.width, 4), round((y - self.top) / self.height, 4)


def find_game_region(window_title: str | None, monitor: int) -> Region:
    """Szuka okna gry po tytule (tylko Windows), w przeciwnym razie używa całego monitora."""
    if window_title and sys.platform == "win32":
        try:
            import pygetwindow as gw

            wins = [w for w in gw.getWindowsWithTitle(window_title) if w.width > 200]
            if wins:
                w = wins[0]
                try:
                    w.activate()
                except Exception:
                    pass
                client = _client_rect(w._hWnd)
                if client:
                    return client
                return Region(w.left, w.top, w.width, w.height)
        except ImportError:
            pass
    with mss.mss() as sct:
        m = sct.monitors[monitor]
        return Region(m["left"], m["top"], m["width"], m["height"])


def _client_rect(hwnd: int) -> Region | None:
    """Obszar okna bez ramki i paska tytułu (ważne w trybie okienkowym)."""
    try:
        from ctypes import wintypes

        rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
        pt = wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
        if rect.right > 0 and rect.bottom > 0:
            return Region(pt.x, pt.y, rect.right, rect.bottom)
    except Exception:
        pass
    return None


class Screen:
    def __init__(self, region: Region, templates_dir: Path, threshold: float, reference_width: int):
        self.region = region
        self.templates_dir = templates_dir
        self.threshold = threshold
        # Szablony wycina się na jednej rozdzielczości; przy innej skalujemy je proporcjonalnie.
        self.scale = region.width / reference_width if reference_width else 1.0
        self._sct = None
        self._cache: dict[str, np.ndarray | None] = {}

    def _shot(self) -> np.ndarray:
        if self._sct is None:
            self._sct = mss.mss()
        r = self.region
        return np.array(self._sct.grab({"left": r.left, "top": r.top, "width": r.width, "height": r.height}))

    def grab(self) -> np.ndarray:
        return cv2.cvtColor(self._shot(), cv2.COLOR_BGRA2GRAY)

    def grab_color(self) -> np.ndarray:
        return cv2.cvtColor(self._shot(), cv2.COLOR_BGRA2BGR)

    def has_template(self, name: str) -> bool:
        return self._template(name) is not None

    def _template(self, name: str) -> np.ndarray | None:
        if name not in self._cache:
            path = self.templates_dir / f"{name}.png"
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) if path.exists() else None
            if img is not None and abs(self.scale - 1.0) > 0.01:
                img = cv2.resize(img, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
            self._cache[name] = img
        return self._cache[name]

    def find(self, name: str, frame: np.ndarray | None = None) -> tuple[float, float] | None:
        """Zwraca względny środek znalezionego szablonu albo None."""
        tpl = self._template(name)
        if tpl is None:
            return None
        frame = self.grab() if frame is None else frame
        if tpl.shape[0] > frame.shape[0] or tpl.shape[1] > frame.shape[1]:
            return None
        res = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < self.threshold:
            return None
        cx = loc[0] + tpl.shape[1] / 2
        cy = loc[1] + tpl.shape[0] / 2
        return cx / frame.shape[1], cy / frame.shape[0]
