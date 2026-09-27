"""Główna pętla bota: wejście do mapy -> postawienie wież -> start -> czekanie na koniec -> powtórka."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .controls import Controls, StopRequested
from .screen import Screen

log = logging.getLogger("btd6bot")


@dataclass
class Stats:
    started: float = field(default_factory=time.monotonic)
    games: int = 0
    wins: int = 0
    losses: int = 0
    timeouts: int = 0

    def summary(self) -> str:
        hours = (time.monotonic() - self.started) / 3600
        return (
            f"gier: {self.games} | wygrane: {self.wins} | przegrane: {self.losses} | "
            f"timeouty: {self.timeouts} | czas: {hours:.2f} h"
        )


class Bot:
    def __init__(self, config: dict[str, Any], strategy: dict[str, Any], screen: Screen, controls: Controls):
        self.cfg = config
        self.strategy = strategy
        self.screen = screen
        self.ctl = controls
        self.timings = config["timings"]
        self.hotkeys = config["hotkeys"]
        self.buttons: dict[str, list[float]] = config.get("buttons", {})
        self.placed: dict[str, tuple[float, float]] = {}
        self.stats = Stats()

    # ------------------------------------------------------------------ pętla
    def run(self, max_games: int | None = None) -> None:
        log.info("Start bota. F8 = stop, F7 = pauza, mysz w lewy górny róg = awaryjny stop.")
        need_navigation = not self.strategy.get("already_in_game", False)
        try:
            while max_games is None or self.stats.games < max_games:
                if need_navigation:
                    log.info("Wchodzę do mapy...")
                    self.run_sequence(self.strategy.get("start_game", []))
                self.wait_until_in_game()
                self.play_one_game()
                result = self.wait_for_game_end()
                self.stats.games += 1
                if result == "victory":
                    self.stats.wins += 1
                    seq = self.strategy.get("after_victory", self.cfg.get("after_victory", []))
                elif result == "defeat":
                    self.stats.losses += 1
                    seq = self.strategy.get("after_defeat", self.cfg.get("after_defeat", []))
                else:
                    self.stats.timeouts += 1
                    seq = self.cfg.get("recovery", [])
                log.info("Wynik: %s. %s", result, self.stats.summary())
                self.run_sequence(seq)
                # Jeśli sekwencja po grze kończy się "Restart", nie trzeba znowu klikać przez menu.
                need_navigation = not self.strategy.get("restart_skips_menu", False) or result == "timeout"
        except StopRequested:
            log.info("Zatrzymano. %s", self.stats.summary())

    # ------------------------------------------------------------------ gra
    def wait_until_in_game(self) -> None:
        if self.screen.has_template("ingame"):
            if not self.wait_for_template("ingame", self.timings["load_timeout"]):
                log.warning("Nie widzę ekranu gry ('ingame'), próbuję mimo to.")
        else:
            self.ctl.sleep(self.timings["load_delay"])
        self.ctl.sleep(self.timings.get("after_load_delay", 1.0))

    def play_one_game(self) -> None:
        self.placed.clear()
        for step in self.strategy["steps"]:
            self.run_step(step)
        log.info("Wieże postawione, startuję rundy (start + przyspieszenie).")
        self.ctl.press(self.hotkeys["play"])
        self.ctl.sleep(0.4)
        self.ctl.press(self.hotkeys["play"])

    def wait_for_game_end(self) -> str:
        deadline = time.monotonic() + self.timings["max_game_minutes"] * 60
        dismiss = self.cfg.get("dismiss_templates", [])
        while time.monotonic() < deadline:
            self.ctl.sleep(self.timings["check_interval"])
            frame = self.screen.grab()
            if self.screen.find("victory", frame):
                return "victory"
            if self.screen.find("defeat", frame):
                return "defeat"
            for name in dismiss:
                pos = self.screen.find(name, frame)
                if pos:
                    log.info("Zamykam okienko '%s'.", name)
                    self.ctl.click(pos)
                    break
        return "timeout"

    # ------------------------------------------------------------------ kroki
    def run_sequence(self, steps: list[dict[str, Any]]) -> None:
        for step in steps:
            self.run_step(step)

    def run_step(self, step: dict[str, Any]) -> None:
        self.ctl.checkpoint()
        if "place" in step:
            self.place(step["place"])
        elif "upgrade" in step:
            self.upgrade(step["upgrade"])
        elif "sell" in step:
            self.select(step["sell"])
            self.ctl.press(self.hotkeys["sell"])
        elif "click" in step:
            self.ctl.click(self.resolve_point(step["click"]))
            self.ctl.sleep(self.timings["menu_delay"])
        elif "click_template" in step:
            name = step["click_template"]
            pos = self.wait_for_template(name, step.get("timeout", self.timings["load_timeout"]))
            if pos:
                self.ctl.click(pos)
                self.ctl.sleep(self.timings["menu_delay"])
            elif not step.get("optional", False):
                log.warning("Nie znaleziono '%s' na ekranie.", name)
        elif "wait_for" in step:
            if not self.wait_for_template(step["wait_for"], step.get("timeout", self.timings["load_timeout"])):
                log.warning("Nie doczekałem się '%s'.", step["wait_for"])
        elif "key" in step:
            self.ctl.press(str(step["key"]), step.get("times", 1))
        elif "wait" in step:
            self.ctl.sleep(float(step["wait"]))
        else:
            raise ValueError(f"Nieznany krok: {step}")

    def place(self, spec: dict[str, Any]) -> None:
        tower = spec["tower"]
        key = self.hotkeys["towers"].get(tower)
        if key is None:
            raise ValueError(f"Brak skrótu klawiszowego dla wieży '{tower}' w config.yaml")
        pos = tuple(spec["at"])
        log.info("Stawiam %s (%s) w %s", spec.get("name", tower), tower, pos)
        self.ctl.move(pos)
        self.ctl.press(key)
        self.ctl.click(pos)
        # Bez Esc tutaj: przy braku zaznaczenia Esc otwiera menu pauzy.
        self.placed[spec.get("name", tower)] = pos

    def select(self, name: str) -> None:
        if name not in self.placed:
            raise ValueError(f"Wieża '{name}' nie została postawiona wcześniej w strategii")
        self.ctl.click(self.placed[name])

    def upgrade(self, spec: dict[str, Any]) -> None:
        name = spec["name"]
        top, mid, bot = spec["path"]
        log.info("Ulepszam %s: %d-%d-%d", name, top, mid, bot)
        self.select(name)
        for key, count in zip(self.hotkeys["upgrades"], (top, mid, bot)):
            self.ctl.press(key, count)
        self.ctl.press(self.hotkeys["deselect"])

    # ------------------------------------------------------------------ pomocnicze
    def resolve_point(self, value: Any) -> tuple[float, float]:
        if isinstance(value, str):
            if value not in self.buttons:
                raise ValueError(f"Nieznany przycisk '{value}' (dodaj go w config.yaml -> buttons)")
            value = self.buttons[value]
        return float(value[0]), float(value[1])

    def wait_for_template(self, name: str, timeout: float) -> tuple[float, float] | None:
        if not self.screen.has_template(name):
            log.warning("Brak szablonu templates/%s.png - pomijam czekanie.", name)
            return None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pos = self.screen.find(name)
            if pos:
                return pos
            self.ctl.sleep(0.5)
        return None
