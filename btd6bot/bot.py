"""Main farming loop: enter map -> place towers -> start -> wait for the end -> repeat.

PL: Główna pętla: wejście na mapę -> postawienie wież -> start -> czekanie na koniec -> powtórka.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from .control import Control, StopRequested
from .vision import TemplateLibrary, to_gray
from .window import GameWindow

log = logging.getLogger("btd6bot")

Point = tuple[float, float]
# Popups closed automatically whenever they show up (plus `dismiss_templates` from config.yaml).
# PL: Okienka zamykane automatycznie, gdy się pojawią (plus `dismiss_templates` z config.yaml).
BUILTIN_POPUPS = ("levelup", "mk_point")
POLL_INTERVAL = 0.15
END_SCREENS = ("victory", "defeat")
# Safety stop: this many defeats in a row, each within QUICK_DEFEAT_SECONDS of the start, means the
# bot is stuck in a loop (e.g. it keeps seeing an old defeat screen), not that the strategy is bad.
# PL: Bezpiecznik: tyle przegranych z rzędu, każda w QUICK_DEFEAT_SECONDS od startu, oznacza pętlę
# (np. bot widzi wciąż stary ekran przegranej), a nie słabą strategię.
QUICK_DEFEAT_LIMIT = 3
QUICK_DEFEAT_SECONDS = 15  # seconds between screen checks while waiting / PL: odstęp między sprawdzeniami ekranu


@dataclass
class Stats:
    """Totals that may span several runs (the GUI keeps one object per session).

    PL: Sumy, które mogą obejmować kilka serii (GUI trzyma jeden obiekt na całą sesję).
    """
    games: int = 0
    wins: int = 0
    losses: int = 0
    timeouts: int = 0
    last_game_seconds: float = 0.0
    finished_runs_seconds: float = 0.0  # running time of finished runs / PL: czas zakończonych serii
    run_started: float | None = None    # set while a run is in progress / PL: ustawione w trakcie serii

    def running_seconds(self) -> float:
        current = time.monotonic() - self.run_started if self.run_started is not None else 0.0
        return self.finished_runs_seconds + current

    def summary(self) -> str:
        return (f"games {self.games} | wins {self.wins} | losses {self.losses} | "
                f"timeouts {self.timeouts} | last {self.last_game_seconds / 60:.1f} min | "
                f"total {self.running_seconds() / 3600:.2f} h")


class Bot:
    def __init__(self, config: dict[str, Any], strategy: dict[str, Any], game: GameWindow,
                 capture, inputs, templates: TemplateLibrary, control: Control,
                 on_stats: Callable[[Stats], None] | None = None, stats: Stats | None = None):
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
        self.stats = stats or Stats()
        self.played = 0  # games in the current run / PL: gry w bieżącej serii

    # ------------------------------------------------------------------ loop / pętla
    def run(self, max_games: int | None = None) -> Stats:
        log.info("Bot started (capture: %s, input: %s). F8 = stop, F7 = pause.",
                 self.capture.name, self.input.name)
        need_menu = not self.strategy.get("start_in_game", False)
        try:
            self.stats.run_started = time.monotonic()
            quick_defeats = 0
            while max_games is None or self.played < max_games:
                self.game.refresh()
                if need_menu:
                    log.info("Entering the map...")
                    self.run_sequence(self.strategy.get("start_game", []))
                game_start = time.monotonic()
                self.wait_until_in_game()
                self.play_one_game()
                result = self.wait_for_game_end()
                quick = result == "defeat" and time.monotonic() - self.rounds_started < QUICK_DEFEAT_SECONDS
                quick_defeats = quick_defeats + 1 if quick else 0
                self.stats.games += 1
                self.played += 1
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
                if quick_defeats >= QUICK_DEFEAT_LIMIT:
                    log.error("%d defeats in a row right after the start - stopping, something is wrong "
                              "(check the 'defeat' and 'ingame' templates). / %d przegranych z rzędu zaraz po "
                              "starcie - zatrzymuję bota, coś jest nie tak (sprawdź szablony 'defeat' i 'ingame').",
                              quick_defeats, quick_defeats)
                    break
                need_menu = not self.after_game(result)
        except StopRequested:
            log.info("Stopped. %s", self.stats.summary())
        finally:
            self._release_input()
            if self.stats.run_started is not None:
                self.stats.finished_runs_seconds += time.monotonic() - self.stats.run_started
                self.stats.run_started = None
        return self.stats

    def after_game(self, result: str) -> bool:
        """Handle the post-game screen. Returns True if a new game is already running.

        After a win BTD6 only offers Home / Preview / Freeplay, so the next game starts from the menu.
        After a defeat the strategy's `on_defeat` decides: restart (default, needs the 'restart'
        template), menu (Home, then the menu again) or stop (stop the bot).
        PL: Obsługa ekranu po grze. Zwraca True, jeśli nowa gra już trwa.
        Po wygranej BTD6 daje tylko Home / Preview / Freeplay, więc kolejna gra startuje z menu.
        Po przegranej decyduje `on_defeat` w strategii: restart (domyślnie, wymaga szablonu 'restart'),
        menu (Home i znowu przez menu) albo stop (zatrzymanie bota).
        """
        on_defeat = self.strategy.get("on_defeat", "restart")
        if result == "defeat" and on_defeat == "stop":
            log.info("Defeat - stopping the bot as set in the strategy (on_defeat: stop).")
            self.control.stop()
            return False
        if (result == "defeat" and on_defeat == "restart" and "after_defeat" not in self.strategy
                and self.templates.exists("restart")):
            with self.input.session():
                restart = self.wait_for_template("restart", 5)
                if restart:
                    self.click(restart)
                    log.info("Restarting the map after the defeat.")
                    if not self.wait_until_gone(("defeat", "restart"), 15):
                        log.warning("The defeat screen is still visible after Restart.")
                    return True
            log.warning("'restart' not found - going back through the menu.")
        self.run_sequence(self.post_game_sequence(result))
        return False

    def post_game_sequence(self, result: str) -> list[dict[str, Any]]:
        key = {"victory": "after_victory", "defeat": "after_defeat"}.get(result, "recovery")
        return self.strategy.get(key, self.cfg.get(key, []))

    # ------------------------------------------------------------------ game / gra
    def wait_until_in_game(self) -> None:
        if self.templates.exists("ingame"):
            if self._wait_for_map(self.timings["load_timeout"]):
                log.info("Map loaded.")
            else:
                log.warning("In-game screen ('ingame') not detected, continuing anyway.")
        else:
            log.info("Waiting %d s for the map to load - capture the 'ingame' template to start right away.",
                     self.timings["load_delay"])
            self.control.sleep(self.timings["load_delay"])
        self.control.sleep(self.timings.get("after_load_delay", 1.0))

    def _wait_for_map(self, timeout: float) -> bool:
        """'ingame' visible (twice in a row) and no end screen on top of it. The 'ingame' element (e.g. the
        heart icon) can also be visible on the victory/defeat screen, which is still fading out after Restart.

        PL: 'ingame' widoczne (dwa razy z rzędu) i żadnego ekranu końca gry. Element 'ingame' (np. serduszko)
        może być widoczny też na ekranie wygranej/przegranej, który po Restart jeszcze znika.
        """
        deadline = time.monotonic() + timeout
        seen = 0
        while time.monotonic() < deadline:
            frame = self.grab_gray()
            if frame is not None:
                end_screen = any(self.templates.find(n, frame) for n in END_SCREENS if self.templates.exists(n))
                seen = seen + 1 if not end_screen and self.templates.find("ingame", frame) else 0
                if seen >= 2:
                    return True
            self.control.sleep(POLL_INTERVAL)
        return False

    def wait_until_gone(self, names: tuple[str, ...], timeout: float) -> bool:
        """Wait until none of the templates is on screen. / PL: Czekaj, aż żadnego szablonu nie będzie na ekranie."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.grab_gray()
            if frame is not None and not any(self.templates.find(n, frame) for n in names if self.templates.exists(n)):
                return True
            self.control.sleep(POLL_INTERVAL)
        return False

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
        # Rounds are running - give the computer back until the game ends.
        # PL: Rundy lecą - oddajemy komputer do końca gry.
        self._release_input()

    def wait_for_game_end(self) -> str:
        started = getattr(self, "rounds_started", time.monotonic())
        deadline = started + self.timings["max_game_minutes"] * 60
        dismiss = self.popups()
        # A game of a fixed strategy takes about the same time, so the end is looked for only after
        # `end_check_delay`. Popups (e.g. level-up, which pauses the game) are handled the whole time.
        # PL: Gra przy stałej strategii trwa mniej więcej tyle samo, więc końca szukamy dopiero po
        # `end_check_delay`. Okienka (np. awans, który pauzuje grę) są obsługiwane przez cały czas.
        end_after = started + float(self.strategy.get("end_check_delay", 0) or 0)
        if end_after > time.monotonic():
            log.info("Looking for the end of the game after %.0f s; popups are handled meanwhile.",
                     end_after - started)
        while time.monotonic() < deadline:
            self.control.sleep(self.timings["check_interval"])
            frame = self.grab_gray()
            if frame is None:
                continue
            # A defeat can happen any time, so it is checked from the start. / PL: Przegrana może być w każdej chwili.
            if self.templates.find("defeat", frame):
                log.info("Defeat detected %.0f s after the rounds started.", time.monotonic() - started)
                return "defeat"
            if time.monotonic() >= end_after and self.templates.find("victory", frame):
                log.info("Victory detected %.0f s after the rounds started.", time.monotonic() - started)
                return "victory"
            if self._close_popups(frame, dismiss):
                self._release_input()
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
                # The next step waits for its own button anyway, so only a short pause is needed.
                # PL: Następny krok i tak czeka na swój przycisk, więc wystarczy krótka pauza.
                self.control.sleep(self.timings.get("after_click_delay", 0.3))
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
        # No Esc to deselect: if the tower was not selected, Esc opens the pause menu and the next clicks
        # land in it (this once switched the game's placement setting). The next tower hotkey or the
        # start key closes the upgrade panel anyway.
        # PL: Bez Esc do odznaczania: jeśli wieża nie była zaznaczona, Esc otwiera menu pauzy i kolejne
        # kliknięcia trafiają w nie (raz przełączyło to ustawienie stawiania wież). Skrót następnej wieży
        # albo klawisz startu i tak zamyka panel ulepszeń.

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
        # The list is static once shown, so a short look per page is enough.
        # PL: Lista po wyświetleniu się nie zmienia, więc na każdej stronie wystarczy krótkie sprawdzenie.
        page_timeout = float(step.get("page_timeout", 1.5))
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
            # Let the page scroll animation finish. / PL: Poczekaj na koniec animacji przewijania.
            self.control.sleep(self.timings.get("page_delay", 0.6))
        return None

    def wait_for_template(self, name: str, timeout: float) -> Point | None:
        """Wait until the template is on screen and stays in place (menus slide in with an animation).
        Popups (e.g. level-up) that show up meanwhile are closed.

        PL: Czeka, aż szablon będzie na ekranie i przestanie się ruszać (menu wjeżdżają z animacją).
        Okienka (np. awans), które pojawią się w międzyczasie, są zamykane.
        """
        if not self.templates.exists(name):
            log.warning("Missing template templates/%s.png - skipping.", name)
            return None
        dismiss = [d for d in self.popups() if d != name]
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            frame = self.grab_gray()
            if frame is not None:
                pos = self.templates.find(name, frame)
                if pos and previous and abs(pos[0] - previous[0]) < 0.005 and abs(pos[1] - previous[1]) < 0.005:
                    return pos
                previous = pos
                if not pos:
                    self._close_popups(frame, dismiss)
            self.control.sleep(POLL_INTERVAL)
        return None

    def _release_input(self) -> None:
        """Give the computer back (burst mode); input backends without release() are fine.
        PL: Oddaj komputer (tryb burst); sterowanie bez release() też jest w porządku."""
        release = getattr(self.input, "release", None)
        if release:
            release()

    def popups(self) -> list[str]:
        configured = list(self.cfg.get("dismiss_templates") or [])
        return configured + [p for p in BUILTIN_POPUPS if p not in configured]

    def _close_popups(self, frame, names: list[str]) -> bool:
        for popup in names:
            pos = self.templates.find(popup, frame)
            if pos:
                log.info("Closing popup '%s'.", popup)
                with self.input.session():
                    self.click(pos)
                return True
        return False
