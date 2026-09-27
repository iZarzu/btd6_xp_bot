"""Command line entry point. / PL: Uruchamianie z linii poleceń.

    python -m btd6bot                                       # configuration window (GUI) / okno konfiguracji
    python -m btd6bot run strategies/infernal_deflation.yaml  # farm without GUI / farmienie bez GUI
    python -m btd6bot test                                  # which templates are visible now / widoczne szablony
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .app import CONFIG_PATH, build_runtime, load_yaml, start_hotkeys
from .control import Control
from .window import enable_dpi_awareness

log = logging.getLogger("btd6bot")


def cmd_run(args, cfg: dict) -> None:
    from .bot import Bot

    strategy = load_yaml(Path(args.strategy))
    rt = build_runtime(cfg)
    control = Control()
    start_hotkeys(control, cfg.get("stop_key", "f8"), cfg.get("pause_key", "f7"))
    for name in ("victory", "defeat"):
        if not rt.templates.exists(name):
            log.warning("Missing templates/%s.png - the bot cannot detect the end of a game! "
                        "Capture it in the GUI. / Brak szablonu - wytnij go w GUI.", name)
    log.info("Starting in %d s... / Start za %d s...", args.delay, args.delay)
    control.sleep(args.delay)
    Bot(cfg, strategy, rt.game, rt.capture, rt.input, rt.templates, control).run(args.games)


def cmd_test(args, cfg: dict) -> None:
    from .vision import to_gray

    rt = build_runtime(cfg, with_input=False)
    frame = rt.capture.grab()
    if frame is None:
        raise SystemExit("Could not capture the game. / Nie udało się przechwycić obrazu gry.")
    gray = to_gray(frame)
    for name in rt.templates.names():
        pos = rt.templates.find(name, gray)
        print(f"  {name:20s} {'VISIBLE at ' + str(pos) if pos else '-'}")


def cmd_gui(args, cfg: dict) -> None:
    from .gui import App

    App(Path(args.config)).mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="btd6bot", description="BTD6 XP farming bot")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="farm in a loop / farmienie w pętli")
    run.add_argument("strategy")
    run.add_argument("--games", type=int, default=None, help="number of games (default: endless)")
    run.add_argument("--delay", type=int, default=3, help="seconds before start")
    sub.add_parser("test", help="list templates visible right now")
    sub.add_parser("gui", help="configuration window (default)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    enable_dpi_awareness()
    cfg = load_yaml(Path(args.config))
    {"run": cmd_run, "test": cmd_test}.get(args.cmd, cmd_gui)(args, cfg)


if __name__ == "__main__":
    main()
