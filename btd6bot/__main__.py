"""Uruchamianie:

    python -m btd6bot run strategies/deflation_example.yaml   # farmienie
    python -m btd6bot pos                                     # F9 = wypisz pozycję myszy
    python -m btd6bot capture victory                         # F9 dwa razy = wytnij szablon
    python -m btd6bot test                                    # sprawdź, które szablony widać teraz
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

import cv2
import yaml
from pynput import keyboard, mouse

from .bot import Bot
from .controls import Controls
from .screen import Screen, enable_dpi_awareness, find_game_region

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("btd6bot")


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def make_screen(cfg: dict):
    region = find_game_region(cfg.get("window_title"), cfg.get("monitor", 1))
    log.info("Obszar gry: %s", region)
    screen = Screen(
        region,
        ROOT / cfg.get("templates_dir", "templates"),
        cfg.get("match_threshold", 0.8),
        cfg.get("templates_reference_width", 0),
    )
    return region, screen


def start_hotkeys(ctl: Controls, stop_key: str, pause_key: str) -> None:
    stop = getattr(keyboard.Key, stop_key)
    pause = getattr(keyboard.Key, pause_key)

    def on_press(key):
        if key == stop:
            log.info("Stop - kończę po bieżącej akcji.")
            ctl.stop_event.set()
            return False
        if key == pause:
            if ctl.pause_event.is_set():
                ctl.pause_event.clear()
                log.info("Wznowiono.")
            else:
                ctl.pause_event.set()
                log.info("Pauza (F7 aby wznowić).")

    keyboard.Listener(on_press=on_press, daemon=True).start()


def cmd_run(args, cfg: dict) -> None:
    strategy = load_yaml(Path(args.strategy))
    region, screen = make_screen(cfg)
    ctl = Controls(region, cfg["timings"]["click_delay"])
    start_hotkeys(ctl, cfg.get("stop_key", "f8"), cfg.get("pause_key", "f7"))
    for name in ("victory", "defeat"):
        if not screen.has_template(name):
            log.warning("Brak templates/%s.png - bot nie rozpozna końca gry! Użyj: python -m btd6bot capture %s", name, name)
    log.info("Za %d s start - przełącz się na okno gry.", args.delay)
    ctl.sleep(args.delay)
    Bot(cfg, strategy, screen, ctl).run(args.games)


def _wait_f9(message: str) -> None:
    print(message)
    done = threading.Event()

    def on_press(key):
        if key == keyboard.Key.f9:
            done.set()
            return False

    with keyboard.Listener(on_press=on_press):
        done.wait()


def cmd_pos(args, cfg: dict) -> None:
    region, _ = make_screen(cfg)
    print("Najedź myszką na miejsce i wciśnij F9 (Ctrl+C kończy). Wynik to [x, y] do wklejenia w YAML.")
    m = mouse.Controller()
    try:
        while True:
            _wait_f9("... czekam na F9")
            rel = region.to_rel(m.position)
            print(f"  at: [{rel[0]}, {rel[1]}]    (piksele: {m.position})")
    except KeyboardInterrupt:
        pass


def cmd_capture(args, cfg: dict) -> None:
    region, screen = make_screen(cfg)
    m = mouse.Controller()
    _wait_f9("Najedź na LEWY GÓRNY róg fragmentu (np. napisu VICTORY) i wciśnij F9")
    x1, y1 = m.position
    _wait_f9("Najedź na PRAWY DOLNY róg i wciśnij F9")
    x2, y2 = m.position
    frame = screen.grab_color()
    x1, x2 = sorted((x1 - region.left, x2 - region.left))
    y1, y2 = sorted((y1 - region.top, y2 - region.top))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        sys.exit("Pusty wycinek - spróbuj jeszcze raz.")
    out = screen.templates_dir / f"{args.name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), crop)
    print(f"Zapisano {out} ({crop.shape[1]}x{crop.shape[0]} px). "
          f"Ustaw templates_reference_width: {region.width} w config.yaml.")


def cmd_test(args, cfg: dict) -> None:
    _, screen = make_screen(cfg)
    frame = screen.grab()
    for path in sorted(screen.templates_dir.glob("*.png")):
        pos = screen.find(path.stem, frame)
        print(f"  {path.stem:20s} {'WIDOCZNY w ' + str(pos) if pos else '-'}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="btd6bot", description="Bot do farmienia XP w BTD6")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="farmienie w pętli")
    p.add_argument("strategy")
    p.add_argument("--games", type=int, default=None, help="ile gier zagrać (domyślnie bez końca)")
    p.add_argument("--delay", type=int, default=5, help="sekundy na przełączenie się do gry")
    sub.add_parser("pos", help="odczyt pozycji myszy (F9)")
    p = sub.add_parser("capture", help="wycięcie szablonu obrazka (F9 x2)")
    p.add_argument("name")
    sub.add_parser("test", help="sprawdź widoczne szablony")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    enable_dpi_awareness()
    cfg = load_yaml(Path(args.config))
    {"run": cmd_run, "pos": cmd_pos, "capture": cmd_capture, "test": cmd_test}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
