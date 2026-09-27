"""Stop / pause flags shared between the bot thread, hotkeys and the GUI.

PL: Flagi stop / pauza współdzielone przez wątek bota, skróty klawiszowe i GUI.
"""
from __future__ import annotations

import threading
import time


class StopRequested(Exception):
    pass


class Control:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def toggle_pause(self) -> bool:
        if self.pause_event.is_set():
            self.pause_event.clear()
        else:
            self.pause_event.set()
        return self.pause_event.is_set()

    def checkpoint(self) -> None:
        """Raise if stop was requested, block while paused. / PL: Przerwij przy stopie, czekaj w pauzie."""
        if self.stop_event.is_set():
            raise StopRequested
        while self.pause_event.is_set():
            if self.stop_event.is_set():
                raise StopRequested
            time.sleep(0.2)

    def sleep(self, seconds: float) -> None:
        """Interruptible sleep. / PL: Czekanie, które można przerwać."""
        end = time.monotonic() + seconds
        while True:
            self.checkpoint()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(0.2, left))
