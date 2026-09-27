"""Mysz i klawiatura. Na Windowsie preferujemy pydirectinput (lepiej działa z grami)."""
from __future__ import annotations

import sys
import threading
import time

import pyautogui

from .screen import Region

pyautogui.FAILSAFE = True  # mysz w lewy górny róg = awaryjne zatrzymanie
pyautogui.PAUSE = 0.05

try:
    if sys.platform != "win32":
        raise ImportError
    import pydirectinput as _keys

    _keys.PAUSE = 0.05
except ImportError:
    _keys = pyautogui


class StopRequested(Exception):
    pass


class Controls:
    def __init__(self, region: Region, click_delay: float):
        self.region = region
        self.click_delay = click_delay
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

    # --- kontrola przebiegu ---------------------------------------------------
    def checkpoint(self) -> None:
        if self.stop_event.is_set():
            raise StopRequested
        while self.pause_event.is_set():
            if self.stop_event.is_set():
                raise StopRequested
            time.sleep(0.2)

    def sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.checkpoint()
            time.sleep(min(0.2, max(0.0, end - time.monotonic())))

    # --- wejście --------------------------------------------------------------
    def move(self, rel: tuple[float, float]) -> None:
        self.checkpoint()
        pyautogui.moveTo(*self.region.to_abs(rel), duration=0.08)

    def click(self, rel: tuple[float, float]) -> None:
        self.move(rel)
        time.sleep(0.05)
        pyautogui.click()
        self.sleep(self.click_delay)

    def press(self, key: str, times: int = 1) -> None:
        for _ in range(times):
            self.checkpoint()
            _keys.press(key)
            self.sleep(self.click_delay)
