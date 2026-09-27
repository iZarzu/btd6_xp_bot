"""Main farming loop: enter map -> place towers -> start -> wait for the end -> repeat.

PL: Główna pętla: wejście na mapę -> postawienie wież -> start -> czekanie na koniec -> powtórka.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .control import Control, StopRequested
from .vision import TemplateLibrary, to_gray
from .window import GameWindow

log = logging.getLogger("btd6bot")

Point = tuple[float, float]


@dataclass
class Stats:
    started: float = field(default_factory=time.monotonic)
    games: int = 0
    wins: int = 0
    losses: int = 0
    timeouts: int = 0
    last_game_seconds: float = 0.0

    def summary(self) -> str:
        hours = (time.monotonic() - self.started) / 3600
        return (f"games {self.games} | wins {self.wins} | losses {self.losses} | "
                f"timeouts {self.timeouts} | last {self.last_game_seconds / 60:.1f} min | total {hours:.2f} h")


class Bot:
    def __init__(self, config: dict[str, Any], strategy: dict[str, Any], game: GameWindow,
                 capture, inputs, templates: TemplateLibrary, control: Control,
                 on_stats: Callable[[Stats], None] | None = None):
        self.cfg = config
        self.strategy = strategy
        self.game = game
        self.capture = capture
        self.input = inputs
        self.templates = templates
        self.control = control
        self.on_stats = on_stats
        self.timings: dict[str, float] = config["timings"]
        self.hotkeys: dict[str, Any] = config["hotkeys"]
        self.buttons: dict[str, list[float]] = config.get("buttons") or {}
        self.placed: dict[str, Point] = {}
        self.stats = Stats()

    # ------------------------------------------------------------------ loop / pętla
    def run(self, max_games: int | None = None) -> Stats:
        log.info("Bot started (capture: %s, input: %s). F8 = stop, F7 = pause.",
                 self.capture.name, self.input.name)
        need_menu = not self.strategy.get("start_in_game", False)
        try:
            while max_games is None or self.stats.games < max_games:
                self.game.refresh()
                if need_menu:
                    log.info("Entering the map...")
                    self.run_sequence(self.strategy.get("start_game", []))
                game_start = time.monotonic()
                self.wait_until_in_game()
                self.play_one_game()
                result = self.wait_for_game_end()
                self.stats.games += 1
                self.stats.last_game_seconds = time.monotonic() - game_start
                if result == "victory":
                    self.stats.wins += 1
                elif result == "defeat":
                    self.stats.losses += 1
                else:
                    self.stats.timeouts += 1
                log.info("Result: %s | %s", result, self.stats.summary())
                if self.on_stats:
                    self.on_stats(self.stats)
                self.run_sequence(self.post_game_sequence(result))
                # After "Restart" we are already back in the game. / PL: Po „Restart” jesteśmy już w grze.
                need_menu = result == "timeout" or not self.strategy.get("restart_skips_menu", False)
        except StopRequested:
            log.info("Stopped. %s", self.stats.summary())
        return self.stats

    def post_game_sequence(self, result: str) -> list[dict[str, Any]]:
        key = {"victory": "after_victory", "defeat": "after_defeat"}.get(result, "recovery")
        return self.strategy.get(key, self.cfg.get(key, []))

    # ------------------------------------------------------------------ game / gra
    def wait_until_in_game(self) -> None:
        if self.templates.exists("ingame"):
            if not self.wait_for_template("ingame", self.timings["load_timeout"]):
                log.warning("In-game screen ('ingame') not detected, continuing anyway.")
        else:
            self.control.sleep(self.timings["load_delay"])
        self.control.sleep(self.timings.get("after_load_delay", 1.0))

    def play_one_game(self) -> None:
        self.placed.clear()
        with self.input.session():
            for step in self.strategy["steps"]:
                self.run_step(step)
            log.info("Towers ready, starting rounds (start + fast forward).")
            self.press(self.hotkeys["play"])
            self.control.sleep(0.4)
            self.press(self.hotkeys["play"])
        self.rounds_started = time.monotonic()

    def wait_for_game_end(self) -> str:
        started = getattr(self, "rounds_started", time.monotonic())
        deadline = started + self.timings["max_game_minutes"] * 60
        dismiss = self.cfg.get("dismiss_templates") or []
        # A game of a fixed strategy takes about the same time - no need to look for the end earlier.
        # PL: Gra przy stałej strategii trwa mniej więcej tyle samo - nie ma sensu szukać końca wcześniej.
        delay = float(self.strategy.get("end_check_delay", 0) or 0)
        if delay > 0:
            log.info("Waiting %d s before checking for the end of the game.", delay)
            self.control.sleep(max(0.0, started + delay - time.monotonic()))
        while time.monotonic() < deadline:
            self.control.sleep(self.timings["check_interval"])
            frame = self.grab_gray()
            if frame is None:
                continue
            if self.templates.find("victory", frame):
                log.info("Victory detected %.0f s after the rounds started.", time.monotonic() - started)
                return "victory"
            if self.templates.find("defeat", frame):
                log.info("Defeat detected %.0f s after the rounds started.", time.monotonic() - started)
                return "defeat"
            for name in dismiss:
                pos = self.templates.find(name, frame)
                if pos:
                    log.info("Closing popup '%s'.", name)
                    with self.input.session():
                        self.click(pos)
                    break
        return "timeout"

    # ------------------------------------------------------------------ steps / kroki
    def run_sequence(self, steps: list[dict[str, Any]]) -> None:
        if not steps:
            return
        with self.input.session():
            for step in steps:
                self.run_step(step)

    def run_step(self, step: dict[str, Any]) -> None:
        self.control.checkpoint()
        if "place" in step:
            self.place(step["place"])
        elif "upgrade" in step:
            self.upgrade(step["upgrade"])
        elif "sell" in step:
            self.select(step["sell"])
            self.press(self.hotkeys["sell"])
        elif "click" in step:
            self.click(self.resolve_point(step["click"]))
            self.control.sleep(self.timings["menu_delay"])
        elif "click_template" in step:
            name = step["click_template"]
            if "next_page" in step:
                pos = self.find_with_paging(name, step)
            else:
                pos = self.wait_for_template(name, step.get("timeout", self.timings["load_timeout"]))
            if pos:
                self.click(pos)
                self.control.sleep(self.timings["menu_delay"])
            elif not step.get("optional", False):
                log.warning("Template '%s' not found on screen.", name)
        elif "wait_for" in step:
            if not self.wait_for_template(step["wait_for"], step.get("timeout", self.timings["load_timeout"])):
                log.warning("Timed out waiting for '%s'.", step["wait_for"])
        elif "key" in step:
            self.press(str(step["key"]), step.get("times", 1))
        elif "wait" in step:
            self.control.sleep(float(step["wait"]))
        else:
            raise ValueError(f"Unknown step / nieznany krok: {step}")

    def place(self, spec: dict[str, Any]) -> None:
        tower = spec["tower"]
        key = self.hotkeys["towers"].get(tower)
        if key is None:
            raise ValueError(f"No hotkey for tower '{tower}' in config.yaml -> hotkeys.towers")
        name = spec.get("name", tower)
        pos = self.resolve_point(spec["at"])
        log.info("Placing %s (%s) at %s", name, tower, pos)
        # Hover first so the tower appears under the cursor, then click to drop it.
        # PL: Najpierw najechanie, żeby wieża pojawiła się pod kursorem, potem klik.
        self.input.move(pos)
        self.press(key)
        self.input.move(pos)
        self.click(pos)
        # No Esc here: with nothing selected Esc opens the pause menu.
        # PL: Bez Esc - gdy nic nie jest zaznaczone, Esc otwiera menu pauzy.
        self.placed[name] = pos

    def select(self, name: str) -> None:
        if name not in self.placed:
            raise ValueError(f"Tower '{name}' was not placed earlier in the strategy")
        self.click(self.placed[name])

    def upgrade(self, spec: dict[str, Any]) -> None:
        name = spec["name"]
        top, middle, bottom = spec["path"]
        log.info("Upgrading %s: %d-%d-%d", name, top, middle, bottom)
        self.select(name)
        for key, count in zip(self.hotkeys["upgrades"], (top, middle, bottom)):
            self.press(key, count)
        self.press(self.hotkeys["deselect"])

    # ------------------------------------------------------------------ helpers / pomocnicze
    def click(self, pos: Point) -> None:
        self.control.checkpoint()
        self.input.click(pos)

    def press(self, key: str, times: int = 1) -> None:
        self.control.checkpoint()
        self.input.press(key, times)

    def resolve_point(self, value: Any) -> Point:
        if isinstance(value, str):
            if value not in self.buttons:
                raise ValueError(f"Unknown button '{value}' (add it to config.yaml -> buttons)")
            value = self.buttons[value]
        return float(value[0]), float(value[1])

    def grab_gray(self):
        frame = self.capture.grab()
        return None if frame is None else to_gray(frame)

    def find_with_paging(self, name: str, step: dict[str, Any]) -> Point | None:
        """Look for a template; if it is not there, click `next_page` and look again.

        `next_page` is a template name (e.g. the right arrow in the map list) or a point [x, y].
        Used for the map list, where the map's page changes whenever new maps are added.
        PL: Szuka szablonu; jeśli go nie ma, klika `next_page` i szuka dalej.
        `next_page` to nazwa szablonu (np. strzałka w prawo na liście map) albo punkt [x, y].
        Przydatne na liście map, bo strona z mapą zmienia się, gdy dochodzą nowe mapy.
        """
        next_page = step["next_page"]
        max_pages = int(step.get("max_pages", 10))
        page_timeout = float(step.get("page_timeout", 3))
        for page in range(max_pages + 1):
            pos = self.wait_for_template(name, page_timeout)
            if pos:
                return pos
            if page == max_pages:
                break
            if isinstance(next_page, str) and next_page not in self.buttons:
                # A template name; wait_for_template warns if it was never captured.
                # PL: Nazwa szablonu; wait_for_template ostrzeże, jeśli nie został wycięty.
                arrow = self.wait_for_template(next_page, page_timeout)
                if arrow is None:
                    log.warning("Next-page button '%s' not found.", next_page)
                    return None
            else:
                arrow = self.resolve_point(next_page)
            log.info("'%s' not on this page, going to the next one (%d/%d).", name, page + 1, max_pages)
            self.click(arrow)
            self.control.sleep(self.timings["menu_delay"])
        return None

    def wait_for_template(self, name: str, timeout: float) -> Point | None:
        if not self.templates.exists(name):
            log.warning("Missing template templates/%s.png - skipping.", name)
            return None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.grab_gray()
            if frame is not None:
                pos = self.templates.find(name, frame)
                if pos:
                    return pos
            self.control.sleep(0.5)
        return None
