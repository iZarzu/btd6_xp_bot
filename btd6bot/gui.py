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
import ctypes
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
from .i18n import LANGUAGES, STRINGS, default_language, translate
from .recorder import ClickCatcher
from .strategy import Monkey, allowed_tiers, is_valid_path, monkeys_from_steps, replace_steps, steps_yaml, unique_name
from .window import IS_WINDOWS

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
        self.monkeys: list[Monkey] = []
        self._monkeys_other = False  # strategy has steps this tab can't show / PL: kroki spoza tej zakładki
        self._placing = 0
        self.catcher: ClickCatcher | None = None
        self._click_events: queue.Queue = queue.Queue()

        self._build_top()
        self.notebook = ttk.Notebook(self)
        self._build_status_bar()  # packed before the notebook so it stays visible / PL: zawsze widoczny
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._build_templates_tab()
        self._build_monkeys_tab()
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
        self.render_monkeys()

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

    # ------------------------------------------------------------------ monkeys / małpki
    def _build_monkeys_tab(self) -> None:
        tab = self.add_tab("tab_monkeys")
        self.tab_monkeys = tab
        self.tw(ttk.Label(tab, wraplength=940, justify="left"), "monkeys_help").pack(anchor="w", padx=6, pady=6)
        self.lbl_monkeys_file = ttk.Label(tab, text="", foreground="#808080")
        self.lbl_monkeys_file.pack(anchor="w", padx=6)
        self.monkeys_frame = ttk.Frame(tab)
        self.monkeys_frame.pack(fill="x", padx=6, pady=6)
        row = ttk.Frame(tab)
        row.pack(fill="x", padx=6, pady=6)
        self.var_new_tower = tk.StringVar()
        self._new_tower_keys: dict[str, str] = {}
        self.cmb_new_tower = ttk.Combobox(row, textvariable=self.var_new_tower, width=24, state="readonly")
        self.cmb_new_tower.pack(side="left")
        self.tw(ttk.Button(row, command=self.add_monkey), "add_monkey").pack(side="left", padx=4)
        self.lbl_monkeys_status = ttk.Label(tab, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_monkeys_status.pack(anchor="w", padx=6, pady=6)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def tower_label(self, tower: str) -> str:
        return self.t(f"tower_{tower}") if f"tower_{tower}" in STRINGS else tower

    def _on_tab_changed(self, _event=None) -> None:
        # The YAML may have been edited by hand in the Strategy tab. / PL: YAML mógł być edytowany ręcznie.
        if self.notebook.select() == str(self.tab_monkeys):
            self.refresh_monkeys()

    def refresh_monkeys(self) -> None:
        try:
            data = yaml.safe_load(self.strategy_text.get("1.0", "end-1c")) or {}
            self.monkeys, self._monkeys_other = monkeys_from_steps(data.get("steps"))
            self.lbl_monkeys_status.configure(text="")
        except (yaml.YAMLError, AttributeError, KeyError, TypeError):
            self.monkeys, self._monkeys_other = [], False
            self.lbl_monkeys_status.configure(text=self.t("yaml_broken"), foreground="#d70015")
        self.render_monkeys()

    def render_monkeys(self) -> None:
        for child in self.monkeys_frame.winfo_children():
            child.destroy()
        name = self.strategy_path.name if self.strategy_path else "-"
        self.lbl_monkeys_file.configure(text=self.t("monkeys_file", name=name))
        towers = sorted((self.cfg.get("hotkeys", {}).get("towers") or {}).keys(), key=self.tower_label)
        self._new_tower_keys = {self.tower_label(t): t for t in towers}
        self.cmb_new_tower.configure(values=list(self._new_tower_keys))
        if self.var_new_tower.get() not in self._new_tower_keys and towers:
            self.var_new_tower.set(self.tower_label(towers[0]))

        f = self.monkeys_frame
        for col, key in enumerate(["col_monkey", "col_top", "col_middle", "col_bottom", "col_position"]):
            ttk.Label(f, text=self.t(key), font=("Segoe UI", 9, "bold")).grid(
                row=0, column=col, padx=6, pady=(0, 4), sticky="w")
        for row, m in enumerate(self.monkeys, start=1):
            i = row - 1
            ttk.Label(f, text=f"{row}. {self.tower_label(m.tower)}  ({m.name})").grid(
                row=row, column=0, padx=6, pady=2, sticky="w")
            for j in range(3):
                tiers = allowed_tiers(m.path, j)
                var = tk.StringVar(value=str(m.path[j]))
                # Only rule-compliant tiers are offered; a locked path is disabled.
                # PL: Do wyboru tylko poziomy zgodne z zasadami; zablokowana ścieżka jest wyłączona.
                combo = ttk.Combobox(f, textvariable=var, values=[str(v) for v in tiers], width=3,
                                     state="readonly" if len(tiers) > 1 else "disabled")
                combo.grid(row=row, column=1 + j, padx=6, pady=2)
                combo.bind("<<ComboboxSelected>>", lambda _e, i=i, j=j, v=var: self.set_tier(i, j, int(v.get())))
            if m.at:
                ttk.Label(f, text=f"[{m.at[0]}, {m.at[1]}]").grid(row=row, column=4, padx=6, sticky="w")
            else:
                ttk.Label(f, text=self.t("not_set"), foreground="#d70015").grid(row=row, column=4, padx=6, sticky="w")
            ttk.Button(f, text=self.t("set_position"), command=lambda i=i: self.set_position(i)).grid(
                row=row, column=5, padx=6, pady=2)
            ttk.Button(f, text="↑", width=3, command=lambda i=i: self.move_monkey(i, -1)).grid(row=row, column=6)
            ttk.Button(f, text="↓", width=3, command=lambda i=i: self.move_monkey(i, 1)).grid(row=row, column=7)
            ttk.Button(f, text="✕", width=3, command=lambda i=i: self.remove_monkey(i)).grid(
                row=row, column=8, padx=(6, 0))

    def apply_monkeys(self) -> bool:
        """Write the monkey list into the strategy (editor + file). / PL: Zapisz listę małpek do strategii."""
        if self._monkeys_other:
            if not messagebox.askyesno(APP_TITLE, self.t("other_steps")):
                self.refresh_monkeys()
                return False
            self._monkeys_other = False
        text = replace_steps(self.strategy_text.get("1.0", "end-1c"), steps_yaml(self.monkeys))
        self.strategy_text.delete("1.0", "end")
        self.strategy_text.insert("1.0", text)
        if self.strategy_path:
            self.strategy_path.write_text(text, encoding="utf-8")
            self.lbl_monkeys_status.configure(text=self.t("monkeys_saved", name=self.strategy_path.name),
                                              foreground="#248a3d")
        self.render_monkeys()
        return True

    def set_tier(self, index: int, path_index: int, tier: int) -> None:
        path = list(self.monkeys[index].path)
        path[path_index] = tier
        if is_valid_path(path):
            self.monkeys[index].path = path
            self.apply_monkeys()

    def add_monkey(self) -> None:
        tower = self._new_tower_keys.get(self.var_new_tower.get())
        if tower:
            self.monkeys.append(Monkey(tower, unique_name(tower, {m.name for m in self.monkeys})))
            self.apply_monkeys()

    def remove_monkey(self, index: int) -> None:
        self.monkeys.pop(index)
        self.apply_monkeys()

    def move_monkey(self, index: int, delta: int) -> None:
        target = index + delta
        if 0 <= target < len(self.monkeys):
            self.monkeys[index], self.monkeys[target] = self.monkeys[target], self.monkeys[index]
            self.apply_monkeys()

    def set_position(self, index: int) -> None:
        """Switch to the game, press the tower hotkey and wait for the user's click.

        PL: Przełącz na grę, wciśnij skrót wieży i czekaj na kliknięcie użytkownika.
        """
        if self.catcher:
            # A previous request is still waiting for a click - start over instead of silently ignoring.
            # PL: Poprzednie ustawianie wciąż czeka na klik - zaczynamy od nowa zamiast po cichu ignorować.
            self.catcher.stop()
            self.catcher = None
            log.info("Set position: previous request cancelled.")
        monkey = self.monkeys[index]
        key = (self.cfg.get("hotkeys", {}).get("towers") or {}).get(monkey.tower)
        if key is None:
            messagebox.showerror(APP_TITLE, self.t("err_unknown_tower", tower=monkey.tower))
            return
        try:
            rt = build_runtime(self.current_cfg(), with_input=False)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        log.info("Set position: %s (hotkey '%s'), game window: %s", monkey.name, key,
                 f"{rt.game.rect.width}x{rt.game.rect.height}" if rt.game.hwnd else "NOT FOUND")
        if IS_WINDOWS and not rt.game.hwnd:
            messagebox.showerror(APP_TITLE, self.t("game_not_found"))
            return
        self._placing = index
        self.catcher = ClickCatcher(rt.game, on_click=lambda rel: self._click_events.put(("click", rel)),
                                    on_cancel=lambda: self._click_events.put(("cancel", None)))
        self.lbl_monkeys_status.configure(text=self.t("place_waiting", monkey=self.tower_label(monkey.tower)),
                                          foreground="#0a60d0")
        self.update_idletasks()
        try:
            from .inputs import ForegroundInput, _bring_to_front

            if IS_WINDOWS and rt.game.hwnd:
                _bring_to_front(rt.game.hwnd)
                time.sleep(0.3)
            game_input = ForegroundInput(rt.game, 0.05)
            game_input.move((0.5, 0.5))  # so the tower appears on the map / PL: żeby wieża pojawiła się na mapie
            game_input.press(str(key))
        except Exception as exc:  # the user can still press the hotkey by hand / PL: można wcisnąć ręcznie
            log.warning("Could not switch to the game / nie udało się przełączyć na grę: %s", exc)
            self.lbl_monkeys_status.configure(text=self.t("place_manual_key", key=key), foreground="#d70015")
        # Listen only from now on, so the click on this button is not caught.
        # PL: Słuchamy dopiero od teraz, żeby nie złapać kliknięcia w ten przycisk.
        catcher = self.catcher
        try:
            catcher.start()
        except Exception as exc:  # never leave a dead catcher behind / PL: nie zostawiaj martwego nasłuchu
            self.catcher = None
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.after(60000, lambda: self._placing_timeout(catcher))

    def _placing_timeout(self, catcher: ClickCatcher) -> None:
        if self.catcher is catcher:
            catcher.stop()
            self.catcher = None
            self.lbl_monkeys_status.configure(text=self.t("place_timeout"), foreground="#d70015")
            self._bring_gui_back()

    def _handle_click_events(self) -> None:
        while not self._click_events.empty():
            kind, rel = self._click_events.get_nowait()
            if self.catcher is None:
                continue
            self.catcher = None
            monkey = self.monkeys[self._placing]
            if kind == "click":
                monkey.at = [rel[0], rel[1]]
                self.apply_monkeys()
                self.lbl_monkeys_status.configure(
                    text=self.t("place_saved", monkey=self.tower_label(monkey.tower), pos=f"[{rel[0]}, {rel[1]}]"),
                    foreground="#248a3d")
            else:
                self.lbl_monkeys_status.configure(text=self.t("place_cancelled"), foreground="#808080")
            self._bring_gui_back()

    def _bring_gui_back(self) -> None:
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        if IS_WINDOWS:
            try:
                from .inputs import _bring_to_front

                _bring_to_front(ctypes.windll.user32.GetParent(self.winfo_id()))
            except Exception:
                pass
        self.focus_force()

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
        self.tw(ttk.Label(tab, wraplength=940, justify="left", foreground="#808080"), "strategy_help").pack(
            anchor="w", padx=6)
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
        self.refresh_monkeys()

    def validate_strategy(self, text: str) -> dict | None:
        try:
            data = yaml.safe_load(text) or {}
            steps = data.get("steps")
            if not isinstance(steps, list) or not steps:
                raise ValueError(self.t("err_steps"))
            towers = (self.cfg.get("hotkeys", {}).get("towers") or {})
            paths: dict[str, list[int]] = {}
            for step in steps:
                if "place" in step:
                    place = step["place"]
                    if place["tower"] not in towers:
                        raise ValueError(self.t("err_unknown_tower", tower=place["tower"]))
                    name = place.get("name", place["tower"])
                    if not (isinstance(place.get("at"), list) and len(place["at"]) == 2):
                        raise ValueError(self.t("err_no_position", name=name))
                    paths[name] = [0, 0, 0]
                if "upgrade" in step:
                    name = step["upgrade"]["name"]
                    if name not in paths:
                        raise ValueError(self.t("err_upgrade_first", name=name))
                    paths[name] = [a + b for a, b in zip(paths[name], step["upgrade"]["path"])]
                    if not is_valid_path(paths[name]):
                        raise ValueError(self.t("err_invalid_path", name=name, path="-".join(map(str, paths[name]))))
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
        self.render_monkeys()

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
        self._handle_click_events()
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
        if self.catcher:
            self.catcher.stop()
        if self.control:
            self.control.stop()
        self.destroy()
