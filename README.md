# Productivity Tracker v2 — Setup Guide

---

## Step 1 — Install dependencies

Open Command Prompt and run:

```
pip install pystray Pillow
```

---

## Step 2 — Test it manually first

```
cd path\to\productivity-tracker-v2
python tracker.py
```

You should see a clock icon appear in your system tray (bottom-right, near the clock).
Right-click it — you'll see Settings, Export CSV, Quit.

Wait for the interval (or temporarily set it to 1 min in Settings to test),
the popup should appear automatically.

---

## Step 3 — Auto-start on Windows login (no terminal window)

1. Press  **Win + R**
2. Type `shell:startup`  and press Enter
3. A folder opens — copy `start_tracker.vbs` into that folder
4. That's it — tracker will start silently on every login

To test it immediately without rebooting:
Double-click `start_tracker.vbs` — it will launch in the background.

---

## Step 4 — Verify it's running

- Look for the clock icon in the system tray
- If you don't see it, click the **^** arrow in the tray to see hidden icons
- Right-click → Settings to configure your interval

---

## Files

```
productivity-tracker-v2/
├── tracker.py          ← everything: loop, popup, tray, export
├── requirements.txt    ← pystray, Pillow
├── start_tracker.vbs   ← silent launcher for Windows startup
├── config.json         ← auto-created on first settings save
└── logs/
    └── productivity_log.csv   ← auto-created on first log entry
```

---

## Popup behaviour

| Scenario                          | entry_type |
|-----------------------------------|------------|
| Submit category + note            | logged     |
| Submit outside 09:00–18:00        | overtime   |
| Close popup without submitting    | missed     |
| 2 consecutive misses (work hours) | break      |
| 12:30–13:30                       | lunch      |

---

## Export CSV

Right-click tray icon → Export CSV
File saves to the `logs/` folder and the folder opens automatically.

Or via command line:
```
python tracker.py export
```

---

## Stop the tracker

Right-click tray icon → Quit

To remove from startup: delete `start_tracker.vbs` from the startup folder.
Win + R → shell:startup → delete the file.
