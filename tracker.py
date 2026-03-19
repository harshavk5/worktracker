"""
Productivity Tracker v2 — Windows Background Process
Threading model:
  Main thread   → Tkinter event loop (all UI)
  Scheduler     → daemon thread, posts to ui_queue
  pystray       → daemon thread
  Communication → queue.Queue polled every 200ms on main thread
"""

import csv
import os
import sys
import time
import threading
import queue
import datetime as dt
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import json

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR     = BASE_DIR / "logs"
LOG_FILE    = LOG_DIR  / "productivity_log.csv"

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "interval_minutes":        30,
    "work_start":              "09:00",
    "work_end":                "18:00",
    "lunch_start":             "12:30",
    "lunch_end":               "13:30",
    "break_threshold_windows": 2
}

CATEGORIES = [
    "Deep Work",
    "Meeting / Call",
    "Review / Feedback",
    "Admin / Email",
    "Learning",
    "Other"
]

CSV_HEADERS = ["date", "time_slot", "day", "category", "note", "entry_type"]

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":        "#1e1e2e",
    "surface":   "#313244",
    "border":    "#45475a",
    "text":      "#cdd6f4",
    "subtext":   "#a6adc8",
    "accent":    "#89b4fa",
    "accent_fg": "#1e1e2e",
    "green":     "#a6e3a1",
    "red":       "#f38ba8",
    "purple":    "#cba6f7",
    "orange":    "#fab387",
}

# ── Config ────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── CSV ───────────────────────────────────────────────────────────────────────
def ensure_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()

def append_row(row: dict):
    ensure_log()
    with open(LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_HEADERS).writerow(row)

def read_rows() -> list:
    ensure_log()
    with open(LOG_FILE, newline="") as f:
        return list(csv.DictReader(f))

def retro_mark_break(n: int):
    rows = read_rows()
    if len(rows) < n:
        return
    tail = rows[-n:]
    if all(r["entry_type"] == "missed" for r in tail):
        for r in tail:
            r["entry_type"] = "break"
        with open(LOG_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            w.writeheader()
            w.writerows(rows)

def export_csv():
    rows = read_rows()
    if not rows:
        return None
    out = LOG_DIR / f"export_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(rows)
    return out

# ── Time helpers ──────────────────────────────────────────────────────────────
def now_minutes() -> int:
    d = dt.datetime.now()
    return d.hour * 60 + d.minute

def parse_hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)

def in_range(now_m: int, start: str, end: str) -> bool:
    return parse_hhmm(start) <= now_m <= parse_hhmm(end)

def today_str()    -> str: return dt.datetime.now().strftime("%Y-%m-%d")
def day_name()     -> str: return dt.datetime.now().strftime("%A")
def current_slot() -> str: return dt.datetime.now().strftime("%H:%M")

# ── UI helpers ────────────────────────────────────────────────────────────────
def styled_button(parent, text, command, style="primary"):
    bg = C["accent"] if style == "primary" else \
         C["border"] if style == "ghost"   else \
         C["red"]    if style == "danger"  else C["accent"]
    fg = C["accent_fg"] if style in ("primary", "danger") else C["text"]
    return tk.Button(parent, text=text, command=command,
                     bg=bg, fg=fg, relief="flat",
                     font=("Segoe UI", 9, "bold"),
                     padx=12, pady=5, cursor="hand2", bd=0,
                     activebackground=bg, activeforeground=fg)

def styled_label(parent, text, size=9, color=None, bold=False):
    return tk.Label(parent, text=text,
                    bg=C["bg"], fg=color or C["subtext"],
                    font=("Segoe UI", size, "bold" if bold else "normal"))

def styled_entry(parent, textvariable, width=34):
    return tk.Entry(parent, textvariable=textvariable,
                    bg=C["surface"], fg=C["text"],
                    insertbackground=C["text"], relief="flat",
                    font=("Segoe UI", 10), width=width,
                    highlightthickness=1,
                    highlightbackground=C["border"],
                    highlightcolor=C["accent"])

def center_window(win, w, h):
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

# ── Tab bar ───────────────────────────────────────────────────────────────────
class TabBar(tk.Frame):
    def __init__(self, parent, tabs, on_switch):
        super().__init__(parent, bg=C["surface"])
        self.on_switch = on_switch
        self.buttons   = {}
        self.active    = tabs[0]
        for name in tabs:
            b = tk.Button(
                self, text=name,
                bg=C["surface"], fg=C["subtext"],
                relief="flat", bd=0,
                font=("Segoe UI", 9, "bold"),
                padx=0, pady=8, cursor="hand2",
                activebackground=C["surface"],
                command=lambda n=name: self._switch(n)
            )
            b.pack(side="left", expand=True, fill="x")
            self.buttons[name] = b
        self._refresh()

    def _switch(self, name):
        self.active = name
        self._refresh()
        self.on_switch(name)

    def _refresh(self):
        for name, btn in self.buttons.items():
            btn.config(fg=C["accent"] if name == self.active else C["subtext"])

# ── Tracker Window ────────────────────────────────────────────────────────────
class TrackerWindow:
    """
    All three tabs in one Toplevel window.
    Must be created on the main thread only.
    countdown_seconds: live countdown shown in Log tab.
    """

    def __init__(self, root, cfg, on_submit, on_dismiss,
                 start_tab="Log", countdown_seconds=0):
        self.cfg               = cfg
        self.on_submit         = on_submit
        self.on_dismiss        = on_dismiss
        self.countdown_seconds = countdown_seconds
        self._jobs             = []

        self.win = tk.Toplevel(root)
        self.win.title("Productivity Tracker")
        self.win.configure(bg=C["bg"])
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._dismiss)
        center_window(self.win, 390, 370)

        # Build all panels first, then switch to start_tab
        self._build()
        self.tab_bar._switch(start_tab)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        self.tab_bar = TabBar(self.win,
                              ["Log", "History", "Settings"],
                              self._on_tab)
        self.tab_bar.pack(fill="x")
        tk.Frame(self.win, bg=C["border"], height=1).pack(fill="x")

        self.container = tk.Frame(self.win, bg=C["bg"])
        self.container.pack(fill="both", expand=True)

        # Build all panels and store — _show_panel controls visibility
        self.panels = {}
        self.panels["Log"]      = self._build_log_panel()
        self.panels["History"]  = self._build_history_panel()
        self.panels["Settings"] = self._build_settings_panel()

    def _on_tab(self, name):
        self._show_panel(name)
        if name == "History":  self._render_history()
        if name == "Settings": self._load_settings()

    def _show_panel(self, name):
        for p in self.panels.values():
            p.pack_forget()
        self.panels[name].pack(fill="both", expand=True, padx=16, pady=12)

    # ── Log panel ─────────────────────────────────────────────────────────────
    def _build_log_panel(self):
        f = tk.Frame(self.container, bg=C["bg"])

        # Top row: clock (left) + meta (centre-left) + countdown (right)
        top_row = tk.Frame(f, bg=C["bg"])
        top_row.pack(fill="x", pady=(0, 10))

        # Live clock
        self.clock_var = tk.StringVar(value="--:--:--")
        self.clock_lbl = tk.Label(
            top_row, textvariable=self.clock_var,
            bg=C["bg"], fg=C["accent"],
            font=("Consolas", 26, "bold")
        )
        self.clock_lbl.pack(side="left")

        # Date + status
        meta = tk.Frame(top_row, bg=C["bg"])
        meta.pack(side="left", padx=(10, 0))
        self.date_var   = tk.StringVar()
        self.status_var = tk.StringVar()
        tk.Label(meta, textvariable=self.date_var,
                 bg=C["bg"], fg=C["subtext"],
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.status_lbl = tk.Label(meta, textvariable=self.status_var,
                                   bg=C["bg"], fg=C["green"],
                                   font=("Segoe UI", 9, "bold"))
        self.status_lbl.pack(anchor="w")

        # Countdown
        cd_frame = tk.Frame(top_row, bg=C["bg"])
        cd_frame.pack(side="right")
        tk.Label(cd_frame, text="next poll",
                 bg=C["bg"], fg=C["subtext"],
                 font=("Segoe UI", 8)).pack(anchor="e")
        self.countdown_var = tk.StringVar(value="--:--")
        self._cd_lbl = tk.Label(cd_frame, textvariable=self.countdown_var,
                                bg=C["bg"], fg=C["subtext"],
                                font=("Consolas", 14, "bold"))
        self._cd_lbl.pack(anchor="e")

        # Category
        styled_label(f, "Category").pack(anchor="w", pady=(0, 3))
        self.cat_var = tk.StringVar(value=CATEGORIES[0])
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
            fieldbackground=C["surface"], background=C["surface"],
            foreground=C["text"], selectbackground=C["surface"],
            selectforeground=C["text"], arrowcolor=C["subtext"])
        ttk.Combobox(f, textvariable=self.cat_var,
                     values=CATEGORIES, state="normal",
                     width=36, font=("Segoe UI", 10),
                     style="Dark.TCombobox").pack(fill="x", pady=(0, 10))

        # Note
        styled_label(f, "Note  (optional)").pack(anchor="w", pady=(0, 3))
        self.note_var = tk.StringVar()
        note_entry = styled_entry(f, self.note_var)
        note_entry.pack(fill="x", pady=(0, 12))
        note_entry.bind("<Return>", lambda e: self._submit())
        note_entry.focus_set()

        # Buttons
        btn_row = tk.Frame(f, bg=C["bg"])
        btn_row.pack(anchor="e")
        styled_button(btn_row, "Skip",     self._dismiss, style="ghost").pack(side="left", padx=(0, 8))
        styled_button(btn_row, "Log it →", self._submit,  style="primary").pack(side="left")

        self.log_toast = tk.Label(f, text="", bg=C["bg"], font=("Segoe UI", 9))
        self.log_toast.pack(pady=(8, 0))

        # Start ticking — panels dict exists at this point
        self._tick_clock()
        self._tick_countdown(self.countdown_seconds)

        return f

    def _tick_clock(self):
        now         = dt.datetime.now()
        now_m       = now.hour * 60 + now.minute
        is_overtime = not in_range(now_m, self.cfg["work_start"], self.cfg["work_end"])
        is_lunch    = in_range(now_m, self.cfg["lunch_start"], self.cfg["lunch_end"])

        color  = C["red"] if is_overtime else C["accent"]
        status = "⚠  Overtime"    if is_overtime else \
                 "🍽  Lunch break" if is_lunch    else \
                 "On the clock"

        self.clock_var.set(now.strftime("%H:%M:%S"))
        self.date_var.set(now.strftime("%a, %d %b"))
        self.status_var.set(status)
        self.clock_lbl.config(fg=color)
        self.status_lbl.config(
            fg=C["red"] if is_overtime else
               C["purple"] if is_lunch else
               C["green"]
        )

        job = self.win.after(1000, self._tick_clock)
        self._jobs.append(job)

    def _tick_countdown(self, remaining: int):
        if remaining < 0:
            remaining = 0

        mins = remaining // 60
        secs = remaining % 60
        self.countdown_var.set(f"{mins:02d}:{secs:02d}")

        color = C["red"]    if remaining <= 60  else \
                C["orange"] if remaining <= 300 else \
                C["subtext"]
        self._cd_lbl.config(fg=color)

        if remaining > 0:
            job = self.win.after(1000, self._tick_countdown, remaining - 1)
            self._jobs.append(job)

    # ── History panel ─────────────────────────────────────────────────────────
    def _build_history_panel(self):
        f = tk.Frame(self.container, bg=C["bg"])

        toolbar = tk.Frame(f, bg=C["bg"])
        toolbar.pack(fill="x", pady=(0, 8))
        styled_label(toolbar, "Today's log", size=10).pack(side="left")
        styled_button(toolbar, "Export CSV ↓", self._export,
                      style="primary").pack(side="right")

        canvas_frame = tk.Frame(f, bg=C["bg"])
        canvas_frame.pack(fill="both", expand=True)

        self.hist_canvas = tk.Canvas(canvas_frame, bg=C["bg"],
                                     highlightthickness=0, height=240)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical",
                                 command=self.hist_canvas.yview)
        self.hist_inner = tk.Frame(self.hist_canvas, bg=C["bg"])
        self.hist_inner.bind("<Configure>", lambda e:
            self.hist_canvas.configure(
                scrollregion=self.hist_canvas.bbox("all")))
        self.hist_canvas.create_window((0, 0), window=self.hist_inner,
                                       anchor="nw")
        self.hist_canvas.configure(yscrollcommand=scrollbar.set)
        self.hist_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        return f

    def _render_history(self):
        for w in self.hist_inner.winfo_children():
            w.destroy()

        today = today_str()
        rows  = sorted(
            [r for r in read_rows() if r["date"] == today],
            key=lambda r: r["time_slot"]
        )

        if not rows:
            tk.Label(self.hist_inner, text="No entries yet today.",
                     bg=C["bg"], fg=C["subtext"],
                     font=("Segoe UI", 10)).pack(pady=20)
            return

        badge_map = {
            "logged":   (C["green"],  "#1e3a2f"),
            "missed":   (C["orange"], "#3a2a1e"),
            "break":    (C["subtext"],C["border"]),
            "lunch":    (C["purple"], "#2a1e3a"),
            "overtime": (C["red"],    "#3a1e2a"),
        }

        for r in rows:
            row_f = tk.Frame(self.hist_inner, bg=C["surface"],
                             pady=5, padx=8)
            row_f.pack(fill="x", pady=2)

            tk.Label(row_f, text=r["time_slot"],
                     bg=C["surface"], fg=C["subtext"],
                     font=("Consolas", 9), width=5,
                     anchor="w").pack(side="left")
            tk.Label(row_f, text=r["category"] or "—",
                     bg=C["surface"], fg=C["text"],
                     font=("Segoe UI", 9, "bold"),
                     anchor="w").pack(side="left", padx=(4, 0))

            et       = r["entry_type"]
            fg_, bg_ = badge_map.get(et, (C["subtext"], C["border"]))
            tk.Label(row_f, text=et,
                     bg=bg_, fg=fg_,
                     font=("Segoe UI", 8, "bold"),
                     padx=5, pady=1).pack(side="right")

            if r["note"]:
                nf = tk.Frame(self.hist_inner, bg=C["surface"])
                nf.pack(fill="x", pady=(0, 2))
                tk.Label(nf, text=f"  ↳ {r['note']}",
                         bg=C["surface"], fg=C["subtext"],
                         font=("Segoe UI", 8), anchor="w").pack(side="left")

    # ── Settings panel ────────────────────────────────────────────────────────
    def _build_settings_panel(self):
        f = tk.Frame(self.container, bg=C["bg"])

        fields = [
            ("Interval (15 or 30 mins)", "s_interval"),
            ("Work start  (HH:MM)",      "s_work_start"),
            ("Work end    (HH:MM)",       "s_work_end"),
            ("Lunch start (HH:MM)",       "s_lunch_start"),
            ("Lunch end   (HH:MM)",       "s_lunch_end"),
        ]
        self.settings_vars = {}
        for label, key in fields:
            styled_label(f, label).pack(anchor="w", pady=(4, 2))
            var = tk.StringVar()
            styled_entry(f, var).pack(fill="x", pady=(0, 2))
            self.settings_vars[key] = var

        bottom = tk.Frame(f, bg=C["bg"])
        bottom.pack(fill="x", pady=(10, 0))
        self.settings_toast = tk.Label(bottom, text="",
                                       bg=C["bg"], fg=C["green"],
                                       font=("Segoe UI", 9))
        self.settings_toast.pack(side="left")
        styled_button(bottom, "Save", self._save_settings,
                      style="primary").pack(side="right")

        tk.Frame(f, bg=C["border"], height=1).pack(fill="x", pady=(12, 8))
        danger = tk.Frame(f, bg=C["bg"])
        danger.pack(fill="x")
        styled_label(danger, "Clear all logged data. Cannot be undone.").pack(side="left")
        styled_button(danger, "Clear", self._clear_data,
                      style="danger").pack(side="right")

        return f

    def _load_settings(self):
        cfg = load_config()
        self.settings_vars["s_interval"].set(cfg["interval_minutes"])
        self.settings_vars["s_work_start"].set(cfg["work_start"])
        self.settings_vars["s_work_end"].set(cfg["work_end"])
        self.settings_vars["s_lunch_start"].set(cfg["lunch_start"])
        self.settings_vars["s_lunch_end"].set(cfg["lunch_end"])

    def _save_settings(self):
        try:
            interval = int(self.settings_vars["s_interval"].get())
            assert interval in (15, 30), "Interval must be 15 or 30"
            cfg = load_config()
            cfg.update({
                "interval_minutes": interval,
                "work_start":  self.settings_vars["s_work_start"].get().strip(),
                "work_end":    self.settings_vars["s_work_end"].get().strip(),
                "lunch_start": self.settings_vars["s_lunch_start"].get().strip(),
                "lunch_end":   self.settings_vars["s_lunch_end"].get().strip(),
            })
            save_config(cfg)
            self.cfg = cfg
            self.settings_toast.config(text="Saved ✓", fg=C["green"])
            self.win.after(2000, lambda: self.settings_toast.config(text=""))
        except Exception as e:
            self.settings_toast.config(text=str(e), fg=C["red"])

    def _clear_data(self):
        if LOG_FILE.exists():
            LOG_FILE.unlink()
        ensure_log()
        self._render_history()

    def _export(self):
        out = export_csv()
        if out:
            os.startfile(str(out.parent))

    # ── Submit / Dismiss ──────────────────────────────────────────────────────
    def _cancel_jobs(self):
        for job in self._jobs:
            try:
                self.win.after_cancel(job)
            except Exception:
                pass
        self._jobs.clear()

    def _submit(self):
        category = self.cat_var.get().strip() or "Other"
        note     = self.note_var.get().strip()
        self._cancel_jobs()
        self.win.destroy()
        self.on_submit(category, note)

    def _dismiss(self):
        self._cancel_jobs()
        self.win.destroy()
        self.on_dismiss()


# ── Scheduler ─────────────────────────────────────────────────────────────────
class Scheduler:
    def __init__(self, ui_queue):
        self.ui_queue           = ui_queue
        self.cfg                = load_config()
        self.consecutive_missed = 0

    def on_submit(self, category, note):
        now_m       = now_minutes()
        is_overtime = not in_range(now_m, self.cfg["work_start"], self.cfg["work_end"])
        append_row({
            "date":       today_str(),
            "time_slot":  current_slot(),
            "day":        day_name(),
            "category":   category,
            "note":       note,
            "entry_type": "overtime" if is_overtime else "logged"
        })
        self.consecutive_missed = 0

    def on_dismiss(self):
        now_m       = now_minutes()
        is_overtime = not in_range(now_m, self.cfg["work_start"], self.cfg["work_end"])
        append_row({
            "date":       today_str(),
            "time_slot":  current_slot(),
            "day":        day_name(),
            "category":   "",
            "note":       "",
            "entry_type": "overtime" if is_overtime else "missed"
        })
        if not is_overtime:
            self.consecutive_missed += 1
            threshold = self.cfg["break_threshold_windows"]
            if self.consecutive_missed >= threshold:
                retro_mark_break(threshold)
                self.consecutive_missed = 0

    def run(self):
        import time as _time
        while True:
            self.cfg     = load_config()
            interval_sec = self.cfg["interval_minutes"] * 60

            # Deadline-based sleep — immune to drift under system load
            # Instead of counting 1800 x 1s ticks, we target a fixed end time
            deadline = _time.monotonic() + interval_sec
            while True:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    break
                # Sleep in small chunks so thread stays responsive
                _time.sleep(min(1.0, remaining))

            self.cfg  = load_config()
            now_m     = now_minutes()
            is_lunch  = in_range(now_m, self.cfg["lunch_start"],
                                        self.cfg["lunch_end"])
            if is_lunch:
                append_row({
                    "date":       today_str(),
                    "time_slot":  current_slot(),
                    "day":        day_name(),
                    "category":   "",
                    "note":       "",
                    "entry_type": "lunch"
                })
                continue

            self.ui_queue.put({
                "action":    "show_popup",
                "tab":       "Log",
                "countdown": self.cfg["interval_minutes"] * 60
            })


# ── App (main thread) ─────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.cfg        = load_config()
        self.ui_queue   = queue.Queue()
        self.scheduler  = Scheduler(self.ui_queue)
        self.active_win = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Productivity Tracker")

    def _open_window(self, start_tab="Log", countdown=0):
        # Window already open — lift and switch tab
        if self.active_win is not None:
            try:
                self.active_win.tab_bar._switch(start_tab)
                self.active_win.win.lift()
                return
            except tk.TclError:
                self.active_win = None

        self.active_win = TrackerWindow(
            root              = self.root,
            cfg               = self.cfg,
            on_submit         = self._on_submit,
            on_dismiss        = self._on_dismiss,
            start_tab         = start_tab,
            countdown_seconds = countdown
        )

    def _on_submit(self, category, note):
        self.active_win = None
        self.scheduler.on_submit(category, note)

    def _on_dismiss(self):
        self.active_win = None
        self.scheduler.on_dismiss()

    def _poll_queue(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()

                if msg["action"] == "show_popup":
                    self._open_window(start_tab=msg["tab"],
                                      countdown=msg.get("countdown", 0))

                elif msg["action"] == "show_history":
                    self._open_window(start_tab="History")

        except queue.Empty:
            pass

        self.root.after(200, self._poll_queue)

    def _build_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            img  = Image.new("RGB", (64, 64), "#1e1e2e")
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, 60, 60],   fill="#89b4fa")
            draw.ellipse([16, 16, 48, 48], fill="#1e1e2e")
            draw.line([32, 32, 32, 22], fill="#89b4fa", width=3)
            draw.line([32, 32, 40, 36], fill="#cdd6f4", width=2)

            def on_click(icon, item):
                self.ui_queue.put({"action": "show_popup",
                                   "tab": "Log", "countdown": 0})

            def open_settings(icon, item):
                self.ui_queue.put({"action": "show_popup",
                                   "tab": "Settings", "countdown": 0})

            def do_export(icon, item):
                out = export_csv()
                if out:
                    os.startfile(str(out.parent))

            def quit_app(icon, item):
                icon.stop()
                self.root.after(0, self.root.destroy)

            menu = pystray.Menu(
                pystray.MenuItem("Log",        on_click, default=True),
                pystray.MenuItem("History",    lambda i, it: i and self.ui_queue.put({"action": "show_history"})),
                pystray.MenuItem("Settings",   open_settings),
                pystray.MenuItem("Export CSV", do_export),
                pystray.MenuItem("Quit",       quit_app),
            )
            return pystray.Icon("ProductivityTracker", img,
                                "Productivity Tracker", menu)
        except ImportError:
            return None

    def run(self):
        # Scheduler — daemon thread
        threading.Thread(target=self.scheduler.run, daemon=True).start()

        # Queue polling — main thread
        self.root.after(200, self._poll_queue)

        # Pystray — daemon thread
        tray = self._build_tray()
        if tray:
            threading.Thread(target=tray.run, daemon=True).start()

        # Tkinter owns the main thread
        self.root.mainloop()


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        out = export_csv()
        print(f"Exported → {out}" if out else "No data.")
    else:
        App().run()
