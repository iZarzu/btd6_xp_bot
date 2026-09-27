"""Configuration / control window (tkinter, bundled with Python).

PL: Okno konfiguracji i sterowania (tkinter, wbudowany w Pythona).

Everything that depends on the screen size (templates, tower positions) is set up by
clicking on a screenshot of YOUR game, and stored in a resolution-independent way.
PL: Wszystko, co zależy od rozdzielczości (szablony, pozycje wież), ustawiasz klikając
na zrzucie ekranu TWOJEJ gry, a zapisywane jest niezależnie od rozdzielczości.
"""
from __future__ import annotations

import base64
import logging
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk
from typing import Callable

import cv2
import numpy as np
import yaml

from .app import STRATEGIES_DIR, build_runtime, load_yaml, start_hotkeys
from .control import Control

log = logging.getLogger("btd6bot")

# (name, required, English description, Polish description)
TEMPLATES = [
    ("victory", True, "'Victory' text on the win screen", "napis 'Victory' po wygranej"),
    ("defeat", True, "text on the defeat screen", "napis na ekranie przegranej"),
    ("next", True, "'Next' button on the win screen", "przycisk 'Next' po wygranej"),
    ("home", True, "home button after a game", "przycisk domku po grze"),
    ("play", True, "'Play' button in the main menu", "'Play' w menu głównym"),
    ("expert", False, "'Expert' map category tab", "zakładka map 'Expert'"),
    ("map", True, "map thumbnail (e.g. Infernal)", "miniatura mapy (np. Infernal)"),
    ("easy", True, "'Easy' difficulty button", "przycisk trudności 'Easy'"),
    ("deflation", True, "'Deflation' mode button", "przycisk trybu 'Deflation'"),
    ("ok", False, "'OK' in the mode rules popup", "'OK' w okienku zasad trybu"),
    ("ingame", False, "static in-game HUD element (speeds up loading)", "stały element HUD w grze"),
    ("levelup", False, "level-up popup", "okienko awansu poziomu"),
    ("restart", False, "'Restart' button (faster loop)", "przycisk 'Restart' (szybsza pętla)"),
    ("confirm", False, "restart confirmation button", "potwierdzenie restartu"),
]

CAPTURE_MODES = ["auto", "window", "screen"]
INPUT_MODES = ["burst", "foreground", "background"]


class QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(self.format(record))


def set_yaml_scalar(text: str, key: str, value: str) -> str:
    """Replace a top-level `key: value` line, keeping its trailing comment.

    PL: Podmienia linię `key: value` najwyższego poziomu, zachowując komentarz.
    """
    pattern = re.compile(rf"^({re.escape(key)}:\s*)([^#\n]*?)(\s*#.*)?$", re.M)
    if pattern.search(text):
        return pattern.sub(lambda m: f"{m.group(1)}{value}{m.group(3) or ''}", text, count=1)
    return f"{key}: {value}\n" + text


def frame_to_photo(frame_bgr: np.ndarray, max_w: int, max_h: int) -> tuple[tk.PhotoImage, float]:
    """Downscale a frame to fit the screen and turn it into a Tk image (no Pillow needed).

    PL: Zmniejsza klatkę do rozmiaru ekranu i zamienia na obraz Tk (bez Pillow).
    """
    h, w = frame_bgr.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    shown = cv2.resize(frame_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, png = cv2.imencode(".png", shown)
    return tk.PhotoImage(data=base64.b64encode(png.tobytes())), scale


class ScreenshotPicker(tk.Toplevel):
    """Shows a game screenshot; pick a point (click) or a region (drag).

    PL: Pokazuje zrzut gry; wskaż punkt (klik) albo obszar (przeciągnij).
    """

    def __init__(self, master: "App", mode: str, on_done: Callable, markers: list[tuple[float, float, str]] = ()):
        super().__init__(master)
        self.master_app = master
        self.mode = mode
        self.on_done = on_done
        self.markers = markers
        self.title("Click a point / Kliknij punkt" if mode == "point" else "Drag a rectangle / Zaznacz prostokąt")
        self.transient(master)
        info = ("Click the spot. Circles = towers already in the strategy. / "
                "Kliknij miejsce. Kółka = wieże już dodane w strategii." if mode == "point" else
                "Drag a SMALL, distinctive fragment (text/icon), then Save. / "
                "Zaznacz MAŁY, charakterystyczny fragment (napis/ikonę), potem Zapisz.")
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=info).pack(side="left", padx=6, pady=4)
        self.coords = ttk.Label(top, text="")
        self.coords.pack(side="left", padx=12)
        ttk.Button(top, text="Refresh / Odśwież", command=self.refresh).pack(side="right", padx=4)
        if mode == "rect":
            ttk.Button(top, text="Save / Zapisz", command=self.save_rect).pack(side="right", padx=4)
        self.canvas = tk.Canvas(self, highlightthickness=0, cursor="crosshair")
        self.canvas.pack()
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.bind("<Escape>", lambda _: self.destroy())
        self.rect_id = None
        self.start = None
        self.selection: tuple[float, float, float, float] | None = None
        self.frame: np.ndarray | None = None
        self.refresh()

    def refresh(self) -> None:
        frame = self.master_app.grab_frame()
        if frame is None:
            self.destroy()
            return
        self.frame = frame
        max_w = int(self.winfo_screenwidth() * 0.9)
        max_h = int(self.winfo_screenheight() * 0.8)
        self.photo, self.scale = frame_to_photo(frame, max_w, max_h)
        self.disp_w, self.disp_h = self.photo.width(), self.photo.height()
        self.canvas.configure(width=self.disp_w, height=self.disp_h)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for x, y, label in self.markers:
            cx, cy = x * self.disp_w, y * self.disp_h
            self.canvas.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, outline="#ff3b30", width=2)
            self.canvas.create_text(cx + 12, cy, text=label, fill="#ff3b30", anchor="w",
                                    font=("Segoe UI", 10, "bold"))
        self.rect_id = None
        self.selection = None

    def rel(self, event) -> tuple[float, float]:
        return (round(min(max(event.x / self.disp_w, 0), 1), 4),
                round(min(max(event.y / self.disp_h, 0), 1), 4))

    def on_motion(self, event) -> None:
        x, y = self.rel(event)
        self.coords.configure(text=f"[{x}, {y}]")

    def on_press(self, event) -> None:
        if self.mode == "point":
            self.on_done(self.rel(event))
            self.destroy()
            return
        self.start = (event.x, event.y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#34c759", width=2)

    def on_drag(self, event) -> None:
        if self.mode != "rect" or not self.start:
            return
        x0, y0 = self.start
        self.canvas.coords(self.rect_id, x0, y0, event.x, event.y)
        self.selection = (min(x0, event.x) / self.disp_w, min(y0, event.y) / self.disp_h,
                          max(x0, event.x) / self.disp_w, max(y0, event.y) / self.disp_h)

    def save_rect(self) -> None:
        if not self.selection or self.frame is None:
            messagebox.showwarning("BTD6 bot", "Drag a rectangle first. / Najpierw zaznacz obszar.", parent=self)
            return
        h, w = self.frame.shape[:2]
        x0, y0, x1, y1 = self.selection
        crop = self.frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        if crop.shape[0] < 6 or crop.shape[1] < 6:
            messagebox.showwarning("BTD6 bot", "Selection too small. / Za mały obszar.", parent=self)
            return
        self.on_done(np.ascontiguousarray(crop), w, h)
        self.destroy()


class App(tk.Tk):
    def __init__(self, config_path: Path):
        super().__init__()
        self.title("BTD6 XP Bot")
        self.geometry("980x720")
        self.config_path = config_path
        self.cfg = load_yaml(config_path)
        self.log_queue: queue.Queue = queue.Queue()
        handler = QueueLogHandler(self.log_queue)
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        self.bot_thread: threading.Thread | None = None
        self.control: Control | None = None
        self.strategy_path: Path | None = None

        self._build_game_frame()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_templates_tab(notebook)
        self._build_strategy_tab(notebook)
        self._build_run_tab(notebook)
        self._build_config_tab(notebook)
        self.after(200, self._poll_log)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ game settings / ustawienia gry
    def _build_game_frame(self) -> None:
        box = ttk.LabelFrame(self, text="Game / Gra")
        box.pack(fill="x", padx=8, pady=8)
        self.var_title = tk.StringVar(value=self.cfg.get("window_title", "BloonsTD6"))
        self.var_capture = tk.StringVar(value=self.cfg.get("capture_mode", "auto"))
        self.var_input = tk.StringVar(value=self.cfg.get("input_mode", "burst"))
        self.var_threshold = tk.DoubleVar(value=self.cfg.get("match_threshold", 0.8))

        row = ttk.Frame(box)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="Window title / Tytuł okna:").pack(side="left")
        ttk.Entry(row, textvariable=self.var_title, width=16).pack(side="left", padx=4)
        ttk.Label(row, text="Capture / Obraz:").pack(side="left", padx=(12, 0))
        ttk.Combobox(row, textvariable=self.var_capture, values=CAPTURE_MODES, width=8,
                     state="readonly").pack(side="left", padx=4)
        ttk.Label(row, text="Input / Sterowanie:").pack(side="left", padx=(12, 0))
        ttk.Combobox(row, textvariable=self.var_input, values=INPUT_MODES, width=11,
                     state="readonly").pack(side="left", padx=4)
        ttk.Label(row, text="Match / Dopasowanie:").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row, textvariable=self.var_threshold, from_=0.5, to=0.99, increment=0.01,
                    width=5).pack(side="left", padx=4)

        row = ttk.Frame(box)
        row.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(row, text="Detect window / Wykryj okno", command=self.detect_window).pack(side="left")
        ttk.Button(row, text="Test input / Test sterowania", command=self.test_input).pack(side="left", padx=4)
        ttk.Button(row, text="Save settings / Zapisz ustawienia", command=self.save_game_settings).pack(side="left")
        self.lbl_window = ttk.Label(row, text="")
        self.lbl_window.pack(side="left", padx=12)

    def current_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(window_title=self.var_title.get(), capture_mode=self.var_capture.get(),
                   input_mode=self.var_input.get(), match_threshold=round(float(self.var_threshold.get()), 2))
        return cfg

    def detect_window(self) -> None:
        try:
            rt = build_runtime(self.current_cfg(), with_input=False)
        except Exception as exc:
            messagebox.showerror("BTD6 bot", str(exc))
            return
        r = rt.game.rect
        where = "window / okno" if rt.game.hwnd else "WHOLE MONITOR (game not found) / CAŁY MONITOR"
        self.lbl_window.configure(text=f"{where}: {r.width}x{r.height}, capture: {rt.capture.name}")

    def save_game_settings(self) -> None:
        text = self.config_path.read_text(encoding="utf-8")
        text = set_yaml_scalar(text, "window_title", f'"{self.var_title.get()}"')
        text = set_yaml_scalar(text, "capture_mode", self.var_capture.get())
        text = set_yaml_scalar(text, "input_mode", self.var_input.get())
        text = set_yaml_scalar(text, "match_threshold", str(round(float(self.var_threshold.get()), 2)))
        self.config_path.write_text(text, encoding="utf-8")
        self.cfg = load_yaml(self.config_path)
        self.config_text.delete("1.0", "end")
        self.config_text.insert("1.0", text)
        log.info("Settings saved. / Zapisano ustawienia.")

    def grab_frame(self) -> np.ndarray | None:
        """Screenshot of the game. With screen capture the GUI hides for a moment.

        PL: Zrzut gry. Przy przechwytywaniu ekranu GUI na chwilę się chowa.
        """
        try:
            rt = build_runtime(self.current_cfg(), with_input=False)
            hide = "window" not in rt.capture.name  # screen capture would include this GUI
            if hide:
                self.withdraw()
                self.update()
                time.sleep(0.4)
            try:
                frame = rt.capture.grab()
            finally:
                if hide:
                    self.deiconify()
        except Exception as exc:
            messagebox.showerror("BTD6 bot", f"Capture failed / błąd przechwytywania:\n{exc}")
            return None
        if frame is None:
            messagebox.showerror("BTD6 bot", "No image - is the game minimized? / Brak obrazu - gra zminimalizowana?")
        return frame

    def test_input(self) -> None:
        """Pick a button (e.g. 'Play') and send one click with the chosen input mode.

        PL: Wskaż przycisk (np. 'Play') i wyślij jedno kliknięcie wybranym trybem sterowania.
        """

        def send(pos):
            try:
                rt = build_runtime(self.current_cfg())
                with rt.input.session():
                    rt.input.click(pos)
                log.info("Test click sent at %s via %s. Did the game react? / Czy gra zareagowała?",
                         pos, rt.input.name)
            except Exception as exc:
                messagebox.showerror("BTD6 bot", str(exc))

        ScreenshotPicker(self, "point", send)

    # ------------------------------------------------------------------ templates / szablony
    def _build_templates_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="1. Templates / Szablony")
        ttk.Label(tab, wraplength=900, justify="left", text=(
            "Open the right game screen (e.g. win screen for 'victory'), select a row and click Capture. "
            "Templates are rescaled automatically for other resolutions.\n"
            "PL: Otwórz w grze odpowiedni ekran (np. wygranej dla 'victory'), zaznacz wiersz i kliknij Wytnij. "
            "Szablony są automatycznie skalowane do innych rozdzielczości.")).pack(anchor="w", padx=6, pady=6)
        cols = ("required", "description", "status", "visible")
        self.tree = ttk.Treeview(tab, columns=cols, height=15)
        self.tree.heading("#0", text="Name / Nazwa")
        self.tree.heading("required", text="Required / Wymagany")
        self.tree.heading("description", text="What to capture / Co wyciąć")
        self.tree.heading("status", text="Captured at / Wycięty przy")
        self.tree.heading("visible", text="Visible now / Widoczny")
        self.tree.column("#0", width=100)
        self.tree.column("required", width=110, anchor="center")
        self.tree.column("description", width=420)
        self.tree.column("status", width=130, anchor="center")
        self.tree.column("visible", width=130, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=6)
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Capture selected / Wytnij zaznaczony", command=self.capture_template).pack(side="left")
        ttk.Button(row, text="Capture custom… / Własny…", command=self.capture_custom).pack(side="left", padx=4)
        ttk.Button(row, text="Delete / Usuń", command=self.delete_template).pack(side="left")
        ttk.Button(row, text="Test on current screen / Test na obecnym ekranie",
                   command=self.test_templates).pack(side="left", padx=4)
        self.refresh_templates()

    def library(self):
        return build_runtime(self.current_cfg(), with_input=False).templates

    def refresh_templates(self, visible: dict[str, str] | None = None) -> None:
        lib = self.library()
        self.tree.delete(*self.tree.get_children())
        known = {t[0] for t in TEMPLATES}
        rows = list(TEMPLATES) + [(n, False, "custom", "własny") for n in lib.names() if n not in known]
        for name, required, en, pl in rows:
            status = lib.info(name) or ("✓" if lib.exists(name) else "✗ missing / brak")
            self.tree.insert("", "end", iid=name, text=name, values=(
                "yes / tak" if required else "no / nie", f"{en} / {pl}", status, (visible or {}).get(name, "")))

    def _save_template(self, name: str):
        def done(crop, width, height):
            path = self.library().save(name, crop, width, height)
            log.info("Saved template %s (%dx%d px) from a %dx%d game. / Zapisano szablon.",
                     path.name, crop.shape[1], crop.shape[0], width, height)
            self.refresh_templates()

        return done

    def capture_template(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("BTD6 bot", "Select a row first. / Najpierw zaznacz wiersz.")
            return
        ScreenshotPicker(self, "rect", self._save_template(sel[0]))

    def capture_custom(self) -> None:
        name = simpledialog.askstring("BTD6 bot", "Template name (a-z, 0-9, _) / Nazwa szablonu:", parent=self)
        if name and re.fullmatch(r"[a-z0-9_]+", name):
            ScreenshotPicker(self, "rect", self._save_template(name))

    def delete_template(self) -> None:
        for name in self.tree.selection():
            self.library().delete(name)
        self.refresh_templates()

    def test_templates(self) -> None:
        from .vision import to_gray

        frame = self.grab_frame()
        if frame is None:
            return
        lib, gray = self.library(), to_gray(frame)
        visible = {n: ("✓ YES / TAK" if lib.find(n, gray) else "-") for n in lib.names()}
        self.refresh_templates(visible)

    # ------------------------------------------------------------------ strategy / strategia
    def _build_strategy_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="2. Strategy / Strategia")
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Label(row, text="File / Plik:").pack(side="left")
        self.var_strategy = tk.StringVar()
        files = sorted(p.name for p in STRATEGIES_DIR.glob("*.yaml"))
        self.cmb_strategy = ttk.Combobox(row, textvariable=self.var_strategy, values=files, width=32, state="readonly")
        self.cmb_strategy.pack(side="left", padx=4)
        self.cmb_strategy.bind("<<ComboboxSelected>>", lambda _: self.load_strategy())
        ttk.Button(row, text="Save / Zapisz", command=self.save_strategy).pack(side="left", padx=4)
        ttk.Button(row, text="Save as… / Zapisz jako…", command=self.save_strategy_as).pack(side="left")

        row = ttk.LabelFrame(tab, text="Add tower at cursor position in the editor / Dodaj wieżę w miejscu kursora")
        row.pack(fill="x", padx=6)
        towers = sorted((self.cfg.get("hotkeys", {}).get("towers") or {}).keys())
        self.var_tower = tk.StringVar(value="sniper")
        self.var_tname = tk.StringVar(value="sniper1")
        self.var_path = [tk.IntVar(value=0) for _ in range(3)]
        ttk.Combobox(row, textvariable=self.var_tower, values=towers, width=10, state="readonly").pack(
            side="left", padx=4, pady=4)
        ttk.Label(row, text="name / nazwa:").pack(side="left")
        ttk.Entry(row, textvariable=self.var_tname, width=10).pack(side="left", padx=4)
        ttk.Label(row, text="upgrades / ulepszenia:").pack(side="left")
        for var in self.var_path:
            ttk.Spinbox(row, textvariable=var, from_=0, to=5, width=3).pack(side="left", padx=1)
        ttk.Button(row, text="Pick position & add / Wskaż miejsce i dodaj", command=self.add_tower).pack(
            side="left", padx=6)
        ttk.Button(row, text="Insert point [x, y] / Wstaw punkt", command=self.insert_point).pack(side="left")

        self.strategy_text = scrolledtext.ScrolledText(tab, font=("Consolas", 10), undo=True)
        self.strategy_text.pack(fill="both", expand=True, padx=6, pady=6)
        if files:
            preferred = "infernal_deflation.yaml" if "infernal_deflation.yaml" in files else files[0]
            self.var_strategy.set(preferred)
            self.load_strategy()

    def load_strategy(self) -> None:
        self.strategy_path = STRATEGIES_DIR / self.var_strategy.get()
        self.strategy_text.delete("1.0", "end")
        self.strategy_text.insert("1.0", self.strategy_path.read_text(encoding="utf-8"))

    def validate_strategy(self, text: str) -> dict | None:
        try:
            data = yaml.safe_load(text) or {}
            steps = data.get("steps")
            if not isinstance(steps, list) or not steps:
                raise ValueError("'steps' must be a non-empty list / 'steps' musi być niepustą listą")
            towers = (self.cfg.get("hotkeys", {}).get("towers") or {})
            names = set()
            for step in steps:
                if "place" in step:
                    if step["place"]["tower"] not in towers:
                        raise ValueError(f"Unknown tower / nieznana wieża: {step['place']['tower']}")
                    names.add(step["place"].get("name", step["place"]["tower"]))
                if "upgrade" in step and step["upgrade"]["name"] not in names:
                    raise ValueError(f"Upgrade before place / ulepszenie przed postawieniem: {step['upgrade']['name']}")
            return data
        except Exception as exc:
            messagebox.showerror("BTD6 bot", f"Strategy error / błąd strategii:\n{exc}")
            return None

    def save_strategy(self) -> None:
        if not self.strategy_path:
            return self.save_strategy_as()
        text = self.strategy_text.get("1.0", "end-1c")
        if self.validate_strategy(text) is not None:
            self.strategy_path.write_text(text, encoding="utf-8")
            log.info("Strategy saved: %s / Zapisano strategię.", self.strategy_path.name)

    def save_strategy_as(self) -> None:
        name = simpledialog.askstring("BTD6 bot", "File name / Nazwa pliku (.yaml):", parent=self)
        if not name:
            return
        self.strategy_path = STRATEGIES_DIR / (name if name.endswith(".yaml") else name + ".yaml")
        self.save_strategy()
        self.cmb_strategy.configure(values=sorted(p.name for p in STRATEGIES_DIR.glob("*.yaml")))
        self.var_strategy.set(self.strategy_path.name)

    def strategy_markers(self) -> list[tuple[float, float, str]]:
        try:
            data = yaml.safe_load(self.strategy_text.get("1.0", "end-1c")) or {}
        except yaml.YAMLError:
            return []
        markers = []
        for step in data.get("steps") or []:
            place = step.get("place") if isinstance(step, dict) else None
            if place and isinstance(place.get("at"), list):
                markers.append((place["at"][0], place["at"][1], place.get("name", place["tower"])))
        return markers

    def add_tower(self) -> None:
        def done(pos):
            name, tower = self.var_tname.get().strip(), self.var_tower.get()
            path = [v.get() for v in self.var_path]
            lines = f"  - place: {{tower: {tower}, name: {name}, at: [{pos[0]}, {pos[1]}]}}\n"
            if any(path):
                lines += f"  - upgrade: {{name: {name}, path: [{path[0]}, {path[1]}, {path[2]}]}}\n"
            self.strategy_text.insert("insert linestart", lines)

        ScreenshotPicker(self, "point", done, self.strategy_markers())

    def insert_point(self) -> None:
        ScreenshotPicker(self, "point", lambda pos: self.strategy_text.insert("insert", f"[{pos[0]}, {pos[1]}]"),
                         self.strategy_markers())

    # ------------------------------------------------------------------ run / uruchamianie
    def _build_run_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="3. Run / Uruchom")
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Label(row, text="Games (0 = endless) / Gier (0 = bez końca):").pack(side="left")
        self.var_games = tk.IntVar(value=0)
        ttk.Spinbox(row, textvariable=self.var_games, from_=0, to=10000, width=6).pack(side="left", padx=4)
        self.btn_start = ttk.Button(row, text="▶ Start", command=self.start_bot)
        self.btn_start.pack(side="left", padx=4)
        ttk.Button(row, text="⏸ Pause / Pauza (F7)", command=self.pause_bot).pack(side="left")
        ttk.Button(row, text="■ Stop (F8)", command=self.stop_bot).pack(side="left", padx=4)
        self.lbl_stats = ttk.Label(tab, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_stats.pack(anchor="w", padx=6)
        self.log_text = scrolledtext.ScrolledText(tab, height=20, state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

    def start_bot(self) -> None:
        if self.bot_thread and self.bot_thread.is_alive():
            return
        text = self.strategy_text.get("1.0", "end-1c")
        strategy = self.validate_strategy(text)
        if strategy is None:
            return
        cfg = self.current_cfg()
        missing = [n for n, req, *_ in TEMPLATES if req and not self.library().exists(n)]
        if missing and not messagebox.askyesno(
                "BTD6 bot", f"Missing required templates / brak wymaganych szablonów:\n{', '.join(missing)}\n\n"
                            "Start anyway? / Uruchomić mimo to?"):
            return
        self.control = Control()
        start_hotkeys(self.control, cfg.get("stop_key", "f8"), cfg.get("pause_key", "f7"))
        games = self.var_games.get() or None
        self.bot_thread = threading.Thread(target=self._bot_main, args=(cfg, strategy, self.control, games),
                                           daemon=True)
        self.bot_thread.start()

    def _bot_main(self, cfg: dict, strategy: dict, control: Control, games: int | None) -> None:
        from .bot import Bot

        try:
            rt = build_runtime(cfg)
            bot = Bot(cfg, strategy, rt.game, rt.capture, rt.input, rt.templates, control,
                      on_stats=lambda s: self.log_queue.put(("stats", s.summary())))
            bot.run(games)
        except Exception as exc:  # show any crash in the log / PL: każdy błąd trafia do logu
            log.exception("Bot crashed / bot przerwał pracę: %s", exc)

    def pause_bot(self) -> None:
        if self.control:
            log.info("Paused / pauza" if self.control.toggle_pause() else "Resumed / wznowiono")

    def stop_bot(self) -> None:
        if self.control:
            self.control.stop()

    def _poll_log(self) -> None:
        while not self.log_queue.empty():
            item = self.log_queue.get_nowait()
            if isinstance(item, tuple):
                self.lbl_stats.configure(text=item[1])
                continue
            self.log_text.configure(state="normal")
            self.log_text.insert("end", item + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(200, self._poll_log)

    # ------------------------------------------------------------------ advanced config / zaawansowane
    def _build_config_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Advanced / Zaawansowane (config.yaml)")
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Save / Zapisz", command=self.save_config_text).pack(side="left")
        ttk.Label(row, text="Timings, hotkeys, post-game sequences / Czasy, skróty, sekwencje po grze").pack(
            side="left", padx=8)
        self.config_text = scrolledtext.ScrolledText(tab, font=("Consolas", 10), undo=True)
        self.config_text.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.config_text.insert("1.0", self.config_path.read_text(encoding="utf-8"))

    def save_config_text(self) -> None:
        text = self.config_text.get("1.0", "end-1c")
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            messagebox.showerror("BTD6 bot", f"YAML error / błąd YAML:\n{exc}")
            return
        self.config_path.write_text(text, encoding="utf-8")
        self.cfg = load_yaml(self.config_path)
        log.info("config.yaml saved. / Zapisano config.yaml.")

    def on_close(self) -> None:
        if self.control:
            self.control.stop()
        self.destroy()
