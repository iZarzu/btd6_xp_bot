"""Shared setup used by both the CLI and the GUI.

PL: Wspólna inicjalizacja używana przez CLI i GUI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .capture import make_capture
from .control import Control
from .inputs import make_input
from .vision import TemplateLibrary
from .window import GameWindow, locate_game

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
STRATEGIES_DIR = ROOT / "strategies"

log = logging.getLogger("btd6bot")


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class Runtime:
    game: GameWindow
    capture: Any
    input: Any
    templates: TemplateLibrary


def build_runtime(cfg: dict[str, Any], with_input: bool = True) -> Runtime:
    game = locate_game(cfg.get("window_title", "BloonsTD6"), cfg.get("monitor", 1))
    if game.hwnd is None:
        log.warning("Game window not found - using the whole monitor %dx%d. "
                    "/ Nie znaleziono okna gry - używam całego monitora.", game.rect.width, game.rect.height)
    else:
        log.info("Game window found / znaleziono okno gry: %dx%d", game.rect.width, game.rect.height)
    ratio = game.rect.width / game.rect.height
    if abs(ratio - 16 / 9) > 0.03:
        log.warning("Game area is not 16:9 (%.2f) - positions may be off. Use a 16:9 window. "
                    "/ Obszar gry nie ma proporcji 16:9 - użyj okna 16:9.", ratio)
    capture = make_capture(cfg.get("capture_mode", "auto"), game)
    inputs = make_input(cfg.get("input_mode", "burst"), game, cfg["timings"]["click_delay"]) if with_input else None
    templates = TemplateLibrary(ROOT / cfg.get("templates_dir", "templates"),
                                cfg.get("match_threshold", 0.8), cfg.get("templates_reference_width", 1920))
    return Runtime(game, capture, inputs, templates)


def start_hotkeys(control: Control, stop_key: str = "f8", pause_key: str = "f7") -> None:
    """Global hotkeys (work even when the game is focused). / PL: Globalne skróty klawiszowe."""
    try:
        from pynput import keyboard
    except Exception:  # no display / missing package / PL: brak pakietu
        log.warning("pynput unavailable - global hotkeys disabled.")
        return
    stop, pause = getattr(keyboard.Key, stop_key), getattr(keyboard.Key, pause_key)

    def on_press(key):
        if key == stop:
            log.info("Stop requested - finishing the current action. / Zatrzymywanie...")
            control.stop()
            return False
        if key == pause:
            paused = control.toggle_pause()
            log.info("Paused / pauza" if paused else "Resumed / wznowiono")
        return None

    keyboard.Listener(on_press=on_press, daemon=True).start()
