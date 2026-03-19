# Productivity Tracker

Local Windows productivity logger. Pops up every 15/30 min during work hours,
logs what you're doing, exports to CSV.

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Run

```bash
python tracker.py
```

Sits in your system tray. Right-click the tray icon for:
- **Settings** — change interval, work hours, lunch window
- **Export CSV** — dumps full log + opens folder
- **Quit**

---

## Export via CLI

```bash
python tracker.py export
```

---

## Log location

```
logs/productivity_log.csv
```

---

## CSV columns

| Column | Description |
|---|---|
| `date` | YYYY-MM-DD |
| `time_slot` | HH:MM of the window |
| `day` | Monday–Friday |
| `category` | What you selected |
| `note` | Free text note |
| `entry_type` | `logged` / `missed` / `break` / `lunch` |

---

## Auto-start on Windows login (optional)

1. Press `Win + R` → type `shell:startup` → Enter
2. Drop a shortcut to `start_tracker.bat` in that folder

---

## Config (config.json — auto-created on first settings save)

```json
{
  "interval_minutes": 30,
  "work_start": "09:00",
  "work_end": "18:00",
  "lunch_start": "12:30",
  "lunch_end": "13:30",
  "break_threshold_windows": 2
}
```

---

## Dependencies

- `pystray` — system tray icon
- `Pillow` — tray icon rendering
- `win10toast` — Windows toast notifications (optional, degrades gracefully)
- `tkinter` — built into Python, no install needed
