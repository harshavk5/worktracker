"""
Productivity Tracker — Local Windows App
Popup every X minutes, logs to CSV, skips lunch, marks breaks.
"""

import csv
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from pathlib import Path
import json

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / "config.json"
LOG_FILE    = Path(__file__).parent / "logs" / "productivity_log.csv"

DEFAULT_CONFIG = {
    "interval_minutes": 30,
    "work_start": "09:00",
    "work_end": "18:00",
    "lunch_start": "12:30",
    "lunch_end": "13:30",
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

# ── Config helpers ─────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── CSV helpers ────────────────────────────────────────────────────────────────
def ensure_log():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()

def append_row(row: dict):
    ensure_log()
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow(row)

def read_all_rows() -> list[dict]:
    ensure_log()
    with open(LOG_FILE, newline="") as f:
        return list(csv.DictReader(f))

def update_last_n_missed_to_break(n: int):
    """Retroactively mark last n consecutive missed rows as break."""
    rows = read_all_rows()
    if len(rows) < n:
        return
    tail = rows[-n:]
    if all(r["entry_type"] == "missed" for r in tail):
        for r in tail:
            r["entry_type"] = "break"
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)

# ── Time helpers ───────────────────────────────────────────────────────────────
def parse_time(t: str) -> tuple[int, int]:
    h, m = t.split(":")
    return int(h), int(m)

def in_work_hours(cfg: dict) -> bool:
    now = datetime.now().time()
    ws = datetime.strptime(cfg["work_start"], "%H:%M").time()
    we = datetime.strptime(cfg["work_end"],   "%H:%M").time()
    return ws <= now <= we

def in_lunch(cfg: dict) -> bool:
    now = datetime.now().time()
    ls = datetime.strptime(cfg["lunch_start"], "%H:%M").time()
    le = datetime.strptime(cfg["lunch_end"],   "%H:%M").time()
    return ls <= now <= le

def current_slot() -> str:
    now = datetime.now()
    return now.strftime("%H:%M")

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def day_name() -> str:
    return datetime.now().strftime("%A")

# ── Windows Toast (best-effort, falls back gracefully) ─────────────────────────
def fire_toast(title: str, message: str):
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5, threaded=True)
    except Exception:
        pass  # toast is optional; popup is the primary UI

# ── Input Popup ────────────────────────────────────────────────────────────────
class LogPopup:
    def __init__(self, cfg: dict, slot: str):
        self.cfg    = cfg
        self.slot   = slot
        self.result = None  # "submitted" | "dismissed"

        self.root = tk.Tk()
        self.root.title("What are you working on?")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_dismiss)
        self._center()
        self._build_ui()

    def _center(self):
        self.root.update_idletasks()
        w, h = 420, 280
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        root = self.root
        root.configure(bg="#1e1e2e")

        # ── Header
        hdr = tk.Frame(root, bg="#313244", pady=8)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text=f"⏱  {self.slot}  —  Log your window",
            bg="#313244", fg="#cdd6f4",
            font=("Segoe UI", 11, "bold")
        ).pack()

        body = tk.Frame(root, bg="#1e1e2e", padx=20, pady=12)
        body.pack(fill="both", expand=True)

        # ── Category
        tk.Label(body, text="Category", bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.cat_var = tk.StringVar(value=CATEGORIES[0])
        cat_combo = ttk.Combobox(
            body, textvariable=self.cat_var,
            values=CATEGORIES, state="normal", width=36,
            font=("Segoe UI", 10)
        )
        cat_combo.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        # ── Note
        tk.Label(body, text="Note  (optional)", bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=(0, 2))

        self.note_var = tk.StringVar()
        note_entry = tk.Entry(
            body, textvariable=self.note_var,
            bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4",
            relief="flat", font=("Segoe UI", 10), width=38
        )
        note_entry.grid(row=3, column=0, sticky="ew", pady=(0, 16))
        note_entry.bind("<Return>", lambda e: self._on_submit())
        note_entry.focus_set()

        # ── Buttons
        btn_frame = tk.Frame(body, bg="#1e1e2e")
        btn_frame.grid(row=4, column=0, sticky="e")

        tk.Button(
            btn_frame, text="Skip", command=self._on_dismiss,
            bg="#45475a", fg="#cdd6f4", relief="flat",
            font=("Segoe UI", 9), padx=12, pady=4, cursor="hand2"
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame, text="Log it →", command=self._on_submit,
            bg="#89b4fa", fg="#1e1e2e", relief="flat",
            font=("Segoe UI", 9, "bold"), padx=12, pady=4, cursor="hand2"
        ).pack(side="left")

        # Style combobox
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
            fieldbackground="#313244", background="#313244",
            foreground="#cdd6f4", selectbackground="#313244",
            selectforeground="#cdd6f4"
        )

    def _on_submit(self):
        category = self.cat_var.get().strip() or "Other"
        note     = self.note_var.get().strip()
        self.result = ("submitted", category, note)
        self.root.destroy()

    def _on_dismiss(self):
        self.result = ("dismissed", "", "")
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result

# ── Settings Window ────────────────────────────────────────────────────────────
class SettingsWindow:
    def __init__(self, cfg: dict, on_save):
        self.cfg     = cfg
        self.on_save = on_save

        self.root = tk.Tk()
        self.root.title("Tracker Settings")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")
        self._center()
        self._build()

    def _center(self):
        self.root.update_idletasks()
        w, h = 360, 320
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _field(self, parent, label, var, row):
        tk.Label(parent, text=label, bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 9)).grid(row=row*2,   column=0, sticky="w", pady=(8,0))
        tk.Entry(parent, textvariable=var, bg="#313244", fg="#cdd6f4",
                 insertbackground="#cdd6f4", relief="flat",
                 font=("Segoe UI", 10), width=32
        ).grid(row=row*2+1, column=0, sticky="ew")

    def _build(self):
        hdr = tk.Frame(self.root, bg="#313244", pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Settings", bg="#313244", fg="#cdd6f4",
                 font=("Segoe UI", 11, "bold")).pack()

        body = tk.Frame(self.root, bg="#1e1e2e", padx=20, pady=10)
        body.pack(fill="both", expand=True)

        self.interval = tk.StringVar(value=str(self.cfg["interval_minutes"]))
        self.wstart   = tk.StringVar(value=self.cfg["work_start"])
        self.wend     = tk.StringVar(value=self.cfg["work_end"])
        self.lstart   = tk.StringVar(value=self.cfg["lunch_start"])
        self.lend     = tk.StringVar(value=self.cfg["lunch_end"])

        self._field(body, "Interval (minutes) — 15 or 30", self.interval, 0)
        self._field(body, "Work start (HH:MM)",             self.wstart,   1)
        self._field(body, "Work end (HH:MM)",               self.wend,     2)
        self._field(body, "Lunch start (HH:MM)",            self.lstart,   3)
        self._field(body, "Lunch end (HH:MM)",              self.lend,     4)

        tk.Button(
            body, text="Save & Restart", command=self._save,
            bg="#89b4fa", fg="#1e1e2e", relief="flat",
            font=("Segoe UI", 9, "bold"), padx=12, pady=6, cursor="hand2"
        ).grid(row=11, column=0, sticky="e", pady=(16, 0))

    def _save(self):
        try:
            interval = int(self.interval.get())
            assert interval in (15, 30), "Interval must be 15 or 30"
            self.cfg.update({
                "interval_minutes": interval,
                "work_start":  self.wstart.get(),
                "work_end":    self.wend.get(),
                "lunch_start": self.lstart.get(),
                "lunch_end":   self.lend.get()
            })
            save_config(self.cfg)
            self.on_save()
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Invalid input", str(e))

    def show(self):
        self.root.mainloop()

# ── System Tray ───────────────────────────────────────────────────────────────
def build_tray(cfg: dict, tracker):
    try:
        import pystray
        from PIL import Image, ImageDraw

        # Simple coloured icon
        img = Image.new("RGB", (64, 64), color="#89b4fa")
        d   = ImageDraw.Draw(img)
        d.rectangle([16, 16, 48, 48], fill="#1e1e2e")

        def open_settings(_):
            threading.Thread(
                target=lambda: SettingsWindow(cfg, tracker.restart).show(),
                daemon=True
            ).start()

        def export_csv(_):
            tracker.export_csv()

        def quit_app(_):
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Settings",   open_settings),
            pystray.MenuItem("Export CSV", export_csv),
            pystray.MenuItem("Quit",       quit_app),
        )
        icon = pystray.Icon("ProductivityTracker", img, "Productivity Tracker", menu)
        return icon
    except ImportError:
        return None

# ── Export ─────────────────────────────────────────────────────────────────────
def export_csv():
    rows = read_all_rows()
    if not rows:
        print("No data to export.")
        return

    export_path = LOG_FILE.parent / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(export_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported → {export_path}")

    # Open folder in Explorer
    try:
        os.startfile(str(export_path.parent))
    except Exception:
        pass

# ── Core Tracker ───────────────────────────────────────────────────────────────
class Tracker:
    def __init__(self):
        self.cfg             = load_config()
        self._stop_event     = threading.Event()
        self._thread         = None
        self.consecutive_missed = 0

    def export_csv(self):
        export_csv()

    def restart(self):
        self.cfg = load_config()
        self._stop_event.set()
        time.sleep(1)
        self._stop_event.clear()
        self._start_loop()

    def _start_loop(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop_event.is_set():
            cfg      = self.cfg
            interval = cfg["interval_minutes"] * 60

            # Wait for the next interval tick
            self._stop_event.wait(timeout=interval)
            if self._stop_event.is_set():
                break

            now  = datetime.now()
            slot = current_slot()

            # Outside work hours — do nothing
            if not in_work_hours(cfg):
                continue

            # Lunch window — log silently, no popup
            if in_lunch(cfg):
                append_row({
                    "date":       today_str(),
                    "time_slot":  slot,
                    "day":        day_name(),
                    "category":   "",
                    "note":       "",
                    "entry_type": "lunch"
                })
                self.consecutive_missed = 0
                continue

            # Fire toast notification
            fire_toast("Productivity Tracker", f"Log your {slot} window")

            # Show input popup (blocking — runs in this thread)
            popup  = LogPopup(cfg, slot)
            result = popup.show()

            if result and result[0] == "submitted":
                _, category, note = result
                append_row({
                    "date":       today_str(),
                    "time_slot":  slot,
                    "day":        day_name(),
                    "category":   category,
                    "note":       note,
                    "entry_type": "logged"
                })
                self.consecutive_missed = 0

            else:
                # Dismissed
                append_row({
                    "date":       today_str(),
                    "time_slot":  slot,
                    "day":        day_name(),
                    "category":   "",
                    "note":       "",
                    "entry_type": "missed"
                })
                self.consecutive_missed += 1

                # Retroactively mark as break if threshold crossed
                threshold = cfg["break_threshold_windows"]
                if self.consecutive_missed >= threshold:
                    update_last_n_missed_to_break(threshold)
                    self.consecutive_missed = 0

    def run(self):
        self._start_loop()

        # Try tray icon
        tray = build_tray(self.cfg, self)
        if tray:
            print("Tracker running — find it in your system tray.")
            tray.run()
        else:
            print("Tracker running — tray unavailable, press Ctrl+C to stop.")
            while True:
                time.sleep(60)

# ── Entry ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_csv()
    else:
        Tracker().run()
