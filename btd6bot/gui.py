"""Configuration / control window (tkinter, bundled with Python).

PL: Okno konfiguracji i sterowania (tkinter, wbudowany w Pythona).

Everything that depends on the screen size (templates, tower positions) is set up by
clicking on a screenshot of YOUR game, and stored in a resolution-independent way.
PL: Wszystko, co zależy od rozdzielczości (szablony, pozycje wież), ustawiasz klikając
na zrzucie ekranu TWOJEJ gry, a zapisywane jest niezależnie od rozdzielczości.

All visible texts come from i18n.py; the language is picked in the top-right corner.
PL: Wszystkie widoczne teksty pochodzą z i18n.py; język wybiera się w prawym górnym rogu.
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

from . import __version__
from .app import STRATEGIES_DIR, build_runtime, load_user_settings, load_yaml, save_user_settings, start_hotkeys
from .control import Control
from .i18n import LANGUAGES, default_language, translate

log = logging.getLogger("btd6bot")

# (name, required) - descriptions are in i18n.py as "tpl_<name>". / PL: opisy są w i18n.py.
TEMPLATES = [
    ("victory", True), ("defeat", True), ("next", True), ("home", True), ("play", True),
    ("expert", False), ("arrow_right", False), ("map", True), ("easy", True), ("deflation", True), ("ok", False),
    ("ingame", False), ("levelup", False), ("restart", False), ("confirm", False),
]

CAPTURE_MODES = ["auto", "window", "screen"]
INPUT_MODES = ["burst", "foreground", "background"]
APP_TITLE = "BTD6 XP Bot"


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
    return text.rstrip("\n") + f"\n{key}: {value}\n"


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
        t = master.t
        self.master_app = master
        self.mode = mode
        self.on_done = on_done
        self.markers = markers
        self.title(t("picker_point_title" if mode == "point" else "picker_rect_title"))
        self.transient(master)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=t("picker_point_help" if mode == "point" else "picker_rect_help")).pack(
            side="left", padx=6, pady=4)
        self.coords = ttk.Label(top, text="")
        self.coords.pack(side="left", padx=12)
        ttk.Button(top, text=t("refresh"), command=self.refresh).pack(side="right", padx=4)
        if mode == "rect":
            ttk.Button(top, text=t("save"), command=self.save_rect).pack(side="right", padx=4)
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
        t = self.master_app.t
        if not self.selection or self.frame is None:
            messagebox.showwarning(APP_TITLE, t("need_rect"), parent=self)
            return
        h, w = self.frame.shape[:2]
        x0, y0, x1, y1 = self.selection
        crop = self.frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        if crop.shape[0] < 6 or crop.shape[1] < 6:
            messagebox.showwarning(APP_TITLE, t("too_small"), parent=self)
            return
        self.on_done(np.ascontiguousarray(crop), w, h)
        self.destroy()


class App(tk.Tk):
    def __init__(self, config_path: Path):
        super().__init__()
        self.title(f"{APP_TITLE} v{__version__}")
        self.geometry("1000x740")
        self.config_path = config_path
        self.cfg = load_yaml(config_path)
        self.lang = load_user_settings().get("language") or default_language()
        if self.lang not in LANGUAGES:
            self.lang = "en"
        # Widgets whose text is re-translated on language change: (widget, key, option).
        # PL: Widżety tłumaczone ponownie przy zmianie języka: (widżet, klucz, opcja).
        self._texts: list[tuple[tk.Widget, str, str]] = []
        self._tabs: list[tuple[ttk.Frame, str]] = []
        self._window_info: tuple | None = None
        self._visible: dict[str, bool] = {}
        self._stats: dict | None = None
        self.log_queue: queue.Queue = queue.Queue()
        log.addHandler(QueueLogHandler(self.log_queue))
        log.setLevel(logging.INFO)
        self.bot_thread: threading.Thread | None = None
        self.control: Control | None = None
        self.strategy_path: Path | None = None

        self._build_top()
        self.notebook = ttk.Notebook(self)
        self._build_status_bar()  # packed before the notebook so it stays visible / PL: zawsze widoczny
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._build_templates_tab()
        self._build_strategy_tab()
        self._build_run_tab()
        self._build_config_tab()
        self.after(200, self._poll_log)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ i18n helpers / tłumaczenia
    def t(self, key: str, **fmt) -> str:
        return translate(self.lang, key, **fmt)

    def tw(self, widget: tk.Widget, key: str, option: str = "text") -> tk.Widget:
        """Set a translated text on a widget and remember it. / PL: Ustaw przetłumaczony tekst i zapamiętaj."""
        widget.configure(**{option: self.t(key)})
        self._texts.append((widget, key, option))
        return widget

    def add_tab(self, key: str) -> ttk.Frame:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=self.t(key))
        self._tabs.append((tab, key))
        return tab

    def set_language(self, lang: str) -> None:
        self.lang = lang
        save_user_settings(language=lang)
        for widget, key, option in self._texts:
            widget.configure(**{option: self.t(key)})
        for tab, key in self._tabs:
            self.notebook.tab(tab, text=self.t(key))
        self._set_tree_headings()
        self.refresh_templates()
        self._show_window_info()
        self._show_stats()

    # ------------------------------------------------------------------ top bar / górny pasek
    def _build_top(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        # Language picker in the top-right corner. / PL: Wybór języka w prawym górnym rogu.
        lang_box = ttk.Frame(top)
        lang_box.pack(side="right", anchor="ne", padx=(8, 0))
        self.tw(ttk.Label(lang_box), "language").pack(side="left")
        self.var_lang = tk.StringVar(value=LANGUAGES[self.lang])
        combo = ttk.Combobox(lang_box, textvariable=self.var_lang, values=list(LANGUAGES.values()),
                             width=9, state="readonly")
        combo.pack(side="left", padx=4)
        by_name = {name: code for code, name in LANGUAGES.items()}
        combo.bind("<<ComboboxSelected>>", lambda _: self.set_language(by_name[self.var_lang.get()]))

        box = self.tw(ttk.LabelFrame(top), "game")
        box.pack(side="left", fill="x", expand=True)
        self.var_title = tk.StringVar(value=self.cfg.get("window_title", "BloonsTD6"))
        self.var_capture = tk.StringVar(value=self.cfg.get("capture_mode", "auto"))
        self.var_input = tk.StringVar(value=self.cfg.get("input_mode", "burst"))
        self.var_threshold = tk.DoubleVar(value=self.cfg.get("match_threshold", 0.8))

        row = ttk.Frame(box)
        row.pack(fill="x", padx=6, pady=4)
        self.tw(ttk.Label(row), "window_title").pack(side="left")
        ttk.Entry(row, textvariable=self.var_title, width=14).pack(side="left", padx=4)
        self.tw(ttk.Label(row), "capture").pack(side="left", padx=(10, 0))
        ttk.Combobox(row, textvariable=self.var_capture, values=CAPTURE_MODES, width=8,
                     state="readonly").pack(side="left", padx=4)
        self.tw(ttk.Label(row), "input").pack(side="left", padx=(10, 0))
        ttk.Combobox(row, textvariable=self.var_input, values=INPUT_MODES, width=11,
                     state="readonly").pack(side="left", padx=4)
        self.tw(ttk.Label(row), "match").pack(side="left", padx=(10, 0))
        ttk.Spinbox(row, textvariable=self.var_threshold, from_=0.5, to=0.99, increment=0.01,
                    width=5).pack(side="left", padx=4)

        row = ttk.Frame(box)
        row.pack(fill="x", padx=6, pady=(0, 6))
        self.tw(ttk.Button(row, command=self.detect_window), "detect").pack(side="left")
        self.tw(ttk.Button(row, command=self.test_input), "test_input").pack(side="left", padx=4)
        self.tw(ttk.Button(row, command=self.save_game_settings), "save_settings").pack(side="left")
        self.lbl_window = ttk.Label(row, text="")
        self.lbl_window.pack(side="left", padx=12)

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=8, pady=(0, 4))
        ttk.Label(bar, text=f"v{__version__}", foreground="#808080").pack(side="right")

    def current_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(window_title=self.var_title.get(), capture_mode=self.var_capture.get(),
                   input_mode=self.var_input.get(), match_threshold=round(float(self.var_threshold.get()), 2))
        return cfg

    def detect_window(self) -> None:
        try:
            rt = build_runtime(self.current_cfg(), with_input=False)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self._window_info = (bool(rt.game.hwnd), rt.game.rect.width, rt.game.rect.height, rt.capture.name)
        self._show_window_info()

    def _show_window_info(self) -> None:
        if not self._window_info:
            return
        found, w, h, cap = self._window_info
        self.lbl_window.configure(text=self.t("win_found", w=w, h=h, cap=cap) if found
                                  else self.t("win_monitor", w=w, h=h))

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
        log.info(self.t("settings_saved"))

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
            messagebox.showerror(APP_TITLE, self.t("capture_failed", err=exc))
            return None
        if frame is None:
            messagebox.showerror(APP_TITLE, self.t("no_image"))
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
                log.info(self.t("test_click_sent", pos=pos, mode=rt.input.name))
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc))

        ScreenshotPicker(self, "point", send)

    # ------------------------------------------------------------------ templates / szablony
    def _build_templates_tab(self) -> None:
        tab = self.add_tab("tab_templates")
        self.tw(ttk.Label(tab, wraplength=940, justify="left"), "templates_help").pack(anchor="w", padx=6, pady=6)
        self.tree = ttk.Treeview(tab, columns=("required", "description", "status", "visible"), height=15)
        self.tree.column("#0", width=100)
        self.tree.column("required", width=90, anchor="center")
        self.tree.column("description", width=420)
        self.tree.column("status", width=130, anchor="center")
        self.tree.column("visible", width=130, anchor="center")
        self._set_tree_headings()
        self.tree.pack(fill="both", expand=True, padx=6)
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        self.tw(ttk.Button(row, command=self.capture_template), "btn_capture").pack(side="left")
        self.tw(ttk.Button(row, command=self.capture_custom), "btn_capture_custom").pack(side="left", padx=4)
        self.tw(ttk.Button(row, command=self.delete_template), "btn_delete").pack(side="left")
        self.tw(ttk.Button(row, command=self.test_templates), "btn_test_templates").pack(side="left", padx=4)
        self.refresh_templates()

    def _set_tree_headings(self) -> None:
        for column, key in (("#0", "col_name"), ("required", "col_required"), ("description", "col_description"),
                            ("status", "col_status"), ("visible", "col_visible")):
            self.tree.heading(column, text=self.t(key))

    def library(self):
        return build_runtime(self.current_cfg(), with_input=False).templates

    def refresh_templates(self) -> None:
        lib = self.library()
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        known = {name for name, _ in TEMPLATES}
        rows = list(TEMPLATES) + [(n, False) for n in lib.names() if n not in known]
        for name, required in rows:
            description = self.t(f"tpl_{name}") if name in known else self.t("custom")
            status = lib.info(name) or ("✓" if lib.exists(name) else self.t("missing"))
            visible = ""
            if name in self._visible:
                visible = self.t("visible_yes") if self._visible[name] else "-"
            self.tree.insert("", "end", iid=name, text=name, values=(
                self.t("yes" if required else "no"), description, status, visible))
        existing = [s for s in selected if self.tree.exists(s)]
        if existing:
            self.tree.selection_set(existing)

    def _save_template(self, name: str):
        def done(crop, width, height):
            path = self.library().save(name, crop, width, height)
            log.info(self.t("template_saved", name=path.name, tw=crop.shape[1], th=crop.shape[0], w=width, h=height))
            self.refresh_templates()

        return done

    def capture_template(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, self.t("select_row"))
            return
        ScreenshotPicker(self, "rect", self._save_template(sel[0]))

    def capture_custom(self) -> None:
        name = simpledialog.askstring(APP_TITLE, self.t("template_name_prompt"), parent=self)
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
        self._visible = {n: bool(lib.find(n, gray)) for n in lib.names()}
        self.refresh_templates()

    # ------------------------------------------------------------------ strategy / strategia
    def _build_strategy_tab(self) -> None:
        tab = self.add_tab("tab_strategy")
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        self.tw(ttk.Label(row), "file").pack(side="left")
        self.var_strategy = tk.StringVar()
        files = sorted(p.name for p in STRATEGIES_DIR.glob("*.yaml"))
        self.cmb_strategy = ttk.Combobox(row, textvariable=self.var_strategy, values=files, width=32, state="readonly")
        self.cmb_strategy.pack(side="left", padx=4)
        self.cmb_strategy.bind("<<ComboboxSelected>>", lambda _: self.load_strategy())
        self.tw(ttk.Button(row, command=self.save_strategy), "save").pack(side="left", padx=4)
        self.tw(ttk.Button(row, command=self.save_strategy_as), "save_as").pack(side="left")

        row = self.tw(ttk.LabelFrame(tab), "add_tower_box")
        row.pack(fill="x", padx=6)
        towers = sorted((self.cfg.get("hotkeys", {}).get("towers") or {}).keys())
        self.var_tower = tk.StringVar(value="sniper")
        self.var_tname = tk.StringVar(value="sniper1")
        self.var_path = [tk.IntVar(value=0) for _ in range(3)]
        ttk.Combobox(row, textvariable=self.var_tower, values=towers, width=10, state="readonly").pack(
            side="left", padx=4, pady=4)
        self.tw(ttk.Label(row), "name").pack(side="left")
        ttk.Entry(row, textvariable=self.var_tname, width=10).pack(side="left", padx=4)
        self.tw(ttk.Label(row), "upgrades").pack(side="left")
        for var in self.var_path:
            ttk.Spinbox(row, textvariable=var, from_=0, to=5, width=3).pack(side="left", padx=1)
        self.tw(ttk.Button(row, command=self.add_tower), "pick_add").pack(side="left", padx=6)
        self.tw(ttk.Button(row, command=self.insert_point), "insert_point").pack(side="left")

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
                raise ValueError(self.t("err_steps"))
            towers = (self.cfg.get("hotkeys", {}).get("towers") or {})
            names = set()
            for step in steps:
                if "place" in step:
                    if step["place"]["tower"] not in towers:
                        raise ValueError(self.t("err_unknown_tower", tower=step["place"]["tower"]))
                    names.add(step["place"].get("name", step["place"]["tower"]))
                if "upgrade" in step and step["upgrade"]["name"] not in names:
                    raise ValueError(self.t("err_upgrade_first", name=step["upgrade"]["name"]))
            return data
        except Exception as exc:
            messagebox.showerror(APP_TITLE, self.t("strategy_error", err=exc))
            return None

    def save_strategy(self) -> None:
        if not self.strategy_path:
            return self.save_strategy_as()
        text = self.strategy_text.get("1.0", "end-1c")
        if self.validate_strategy(text) is not None:
            self.strategy_path.write_text(text, encoding="utf-8")
            log.info(self.t("strategy_saved", name=self.strategy_path.name))

    def save_strategy_as(self) -> None:
        name = simpledialog.askstring(APP_TITLE, self.t("file_name_prompt"), parent=self)
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
    def _build_run_tab(self) -> None:
        tab = self.add_tab("tab_run")
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        self.tw(ttk.Label(row), "games").pack(side="left")
        self.var_games = tk.IntVar(value=0)
        ttk.Spinbox(row, textvariable=self.var_games, from_=0, to=10000, width=6).pack(side="left", padx=4)
        self.tw(ttk.Button(row, command=self.start_bot), "start").pack(side="left", padx=4)
        self.tw(ttk.Button(row, command=self.pause_bot), "pause").pack(side="left")
        self.tw(ttk.Button(row, command=self.stop_bot), "stop").pack(side="left", padx=4)
        self.lbl_stats = ttk.Label(tab, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_stats.pack(anchor="w", padx=6)
        self.log_text = scrolledtext.ScrolledText(tab, height=20, state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

    def start_bot(self) -> None:
        if self.bot_thread and self.bot_thread.is_alive():
            return
        strategy = self.validate_strategy(self.strategy_text.get("1.0", "end-1c"))
        if strategy is None:
            return
        cfg = self.current_cfg()
        lib = self.library()
        missing = [name for name, required in TEMPLATES if required and not lib.exists(name)]
        if missing and not messagebox.askyesno(APP_TITLE, self.t("missing_templates", names=", ".join(missing))):
            return
        self.control = Control()
        start_hotkeys(self.control, cfg.get("stop_key", "f8"), cfg.get("pause_key", "f7"))
        games = self.var_games.get() or None
        self.bot_thread = threading.Thread(target=self._bot_main, args=(cfg, strategy, self.control, games),
                                           daemon=True)
        self.bot_thread.start()

    def _bot_main(self, cfg: dict, strategy: dict, control: Control, games: int | None) -> None:
        from .bot import Bot

        def on_stats(s) -> None:
            # Snapshot, the GUI thread formats it in the current language.
            # PL: Kopia danych - wątek GUI formatuje ją w bieżącym języku.
            self.log_queue.put(("stats", {
                "games": s.games, "wins": s.wins, "losses": s.losses, "timeouts": s.timeouts,
                "last": s.last_game_seconds / 60, "hours": (time.monotonic() - s.started) / 3600}))

        try:
            rt = build_runtime(cfg)
            Bot(cfg, strategy, rt.game, rt.capture, rt.input, rt.templates, control, on_stats=on_stats).run(games)
        except Exception as exc:  # show any crash in the log / PL: każdy błąd trafia do logu
            log.exception(self.t("bot_crashed", err=exc))

    def pause_bot(self) -> None:
        if self.control:
            log.info(self.t("paused" if self.control.toggle_pause() else "resumed"))

    def stop_bot(self) -> None:
        if self.control:
            self.control.stop()

    def _show_stats(self) -> None:
        if self._stats:
            self.lbl_stats.configure(text=self.t("stats", **self._stats))

    def _poll_log(self) -> None:
        while not self.log_queue.empty():
            item = self.log_queue.get_nowait()
            if isinstance(item, tuple):
                self._stats = item[1]
                self._show_stats()
                continue
            self.log_text.configure(state="normal")
            self.log_text.insert("end", item + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(200, self._poll_log)

    # ------------------------------------------------------------------ advanced config / zaawansowane
    def _build_config_tab(self) -> None:
        tab = self.add_tab("tab_advanced")
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        self.tw(ttk.Button(row, command=self.save_config_text), "save").pack(side="left")
        self.tw(ttk.Label(row), "advanced_help").pack(side="left", padx=8)
        self.config_text = scrolledtext.ScrolledText(tab, font=("Consolas", 10), undo=True)
        self.config_text.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.config_text.insert("1.0", self.config_path.read_text(encoding="utf-8"))

    def save_config_text(self) -> None:
        text = self.config_text.get("1.0", "end-1c")
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            messagebox.showerror(APP_TITLE, self.t("yaml_error", err=exc))
            return
        self.config_path.write_text(text, encoding="utf-8")
        self.cfg = load_yaml(self.config_path)
        log.info(self.t("config_saved"))

    def on_close(self) -> None:
        if self.control:
            self.control.stop()
        self.destroy()
