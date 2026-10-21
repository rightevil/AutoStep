# AutoStep

**Record mouse clicks and text input once, then replay them on a schedule — unattended, in the background.**

AutoStep is a small Windows tray application built for driving the **Codex** panel inside the ChatGPT desktop app on a timer. You record a sequence of actions (click a region, type a prompt, press Enter), attach that sequence to a schedule, and AutoStep stays quietly in the system tray until the scheduled moment, then performs the whole sequence on the live window.

English | [简体中文](README.md)

---

## Why it exists

Asking an AI coding agent the same thing every night (a nightly refactor prompt, a daily summary request, a repeatable "run the tests and report" job) means being in front of the machine at the right minute. AutoStep turns that into a recorded macro plus a schedule:

- **You record the intent once.** No prompt templates in a config file, no API keys — it drives the real GUI.
- **It survives sleep.** A waitable timer wakes the machine ahead of time so the run is not silently missed.
- **It stays out of the way.** Hidden in the tray, single instance, no console window.

## Features

| | |
|---|---|
| **Region recording** | Click actions are captured by dragging a box over a live screenshot of the target window — no coordinate guessing. |
| **Text input with CJK support** | Pure-ASCII text is typed key by key; anything containing non-ASCII is pasted through the clipboard (original clipboard content is restored). |
| **Key actions** | `enter`, `ctrl+enter`, `tab`, arrows, and arbitrary `ctrl+shift+x` style combos. |
| **DPI-safe coordinates** | Positions are stored as *percentages of the window's client area*, so moving, resizing or maximising the window never shifts the click. |
| **Multiple sequences** | Keep several action sets, rename them, share one sequence between many schedules. |
| **Editable schedules** | Name, date (with a month-view picker), time, once / daily, and which sequence to run. Every plan is re-scheduled automatically after editing. |
| **Sleep-aware** | Arms a waitable timer to wake the system ~90 s before a run, plus a wall-clock catch-up check. |
| **Evidence** | Each run appends to a daily log and can save a screenshot of the final state. |
| **Tray residence** | Closing the window hides it to the tray; optional start-with-Windows via the `Run` registry key. |

## Requirements

- Windows 10 / 11 (relies on Win32 APIs — `pywin32`)
- Python 3.13 (pinned in `mise.toml`; any 3.10+ should work)
- Optional: [mise](https://mise.jdx.dev/) for automatic toolchain setup

Runtime dependencies: `mss`, `Pillow`, `pywin32`, `pyperclip`, `pystray` (about 15 MB total). The UI is plain `tkinter`, so nothing extra to install.

## Installation

```bash
git clone https://github.com/rightevil/AutoStep.git
cd AutoStep
```

With mise (recommended):

```bash
mise install      # installs Python 3.13 per mise.toml
mise run install  # creates .venv and installs requirements.txt
```

Without mise:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Usage

### 1. Launch

From the project directory:

```bash
mise run start
```

Or run the interpreter from the virtualenv directly — `pythonw` keeps the console window out of the way, which is what you want for a background resident:

```bash
.venv\Scripts\pythonw.exe main.py
```

While debugging, use `python` instead of `pythonw` so tracebacks land in the terminal:

```bash
.venv\Scripts\python.exe main.py
```

A normal window opens. Closing it minimises AutoStep to the tray by default and scheduling continues; the tray icon's context menu offers **Show window**, **Run current sequence** and **Quit**. To launch straight into the background from a shortcut, point it at `pythonw.exe` with `main.py`, or tick **Start with Windows** in the UI.

### 2. Pick the target window

AutoStep defaults to the process **`ChatGPT`** — the Codex panel lives inside the ChatGPT desktop app, and its window title changes, so it is matched by process name only.

- **Refresh** — re-enumerate windows (a dropdown of `process — title`).
- **Check** — confirm a window matches and show its client-area size. A green `✓` means the handle is valid.

### 3. Record actions

A *sequence* is an ordered list of actions; top-to-bottom is the execution order.

| Button | What it does |
|---|---|
| **+ Click** | Activates the target window, grabs a screenshot of its client area, and overlays a translucent selector. **Drag a box** over the spot to click; release to record. `Esc` or right-click cancels. |
| **+ Type** | Same region selection (pick the input box), then a dialog for the text to send — multi-line and mixed Chinese/English are fine. "Clear with Ctrl+A first" is enabled by default. |
| **+ Key** | Sends a keystroke or combo, e.g. `enter`, `ctrl+enter`. **Do not forget this step** — typing a prompt without sending it does nothing. |

Reorder with **Up / Down**, tweak an entry with **Edit** (double-click a row), remove with **Delete**. Use **Run once now** to rehearse the sequence immediately; watch the log pane at the bottom.

To add another independent set of actions, use **New** in the sequence row. Rename or delete sequences there too — schedules reference a sequence, so editing a sequence updates every schedule that uses it.

### 4. Create a schedule

Click **+ New plan**:

| Field | Notes |
|---|---|
| Name | Free text, e.g. `nightly refactor` |
| Date | Read-only field plus a **📅 Select** button that opens a month calendar (with a "Today" shortcut) |
| Time | Hour / minute dropdowns, still editable by hand |
| Repeat | **Once** or **Every day at the same time** |
| Sequence | Which recorded action set to run |

Scheduling semantics are deliberately dumb — AutoStep only does what you configured:

- **Once** — fires at the given moment, then the plan is marked *done* and will not fire again. The record is **kept**, never deleted; re-enable it manually if you want another run.
- **Every day** — fires once per day at the given time. Days that were missed (machine off, asleep) are **not** back-filled, so you never get a burst of catch-up runs.
- The date/time you typed is never rewritten by the app.
- Every plan row shows the sequence it uses, its state (`pending` / `done` / `disabled` / `expired`), next fire time, and the result of the last run.
- Select a plan and press **Edit** (or double-click) to change anything; saving re-computes the next fire time and re-enables the plan if the new time is in the future.

### 5. Tune execution

| Setting | Meaning |
|---|---|
| Step delay (s) | Fixed pause between two actions. Use **≥ 1.5** for prompts that trigger network work. |
| Wait after activate (s) | Extra settle time after bringing the window to the foreground. |
| Input mode | `auto` (ASCII → keystrokes, non-ASCII → clipboard paste), `keys` (force per-character), `paste` (force clipboard). |
| Clear with Ctrl+A first | Prevents appending to leftover text. |
| Screenshot after run | Saves a PNG to `data/shots/`. |
| Wake system before run | Uses a waitable timer to wake the machine ~90 s early. |
| Minimise to tray on close | Closing the window keeps the scheduler alive in the tray. |
| Start with Windows | Writes a value to `HKCU\...\CurrentVersion\Run`. |

Once configured, leave AutoStep in the tray. Tray menu: **Show window**, **Run current sequence**, **Quit**.

## How it works

```
main.py               entry point: per-monitor DPI awareness, single-instance mutex, UI start
core/config.py        paths, default settings, app identity (single source for APP_NAME / APP_ID)
core/winsys.py        window enumeration/activation, coordinate mapping, sleep prevention,
                      waitable-timer wake, lock-screen detection
core/capture.py       client-area screenshot + translucent drag-to-select overlay
core/executor.py      action replay: click / Unicode key-by-key typing / clipboard paste / combos
core/scheduler.py     timer loop, wake arming, plan firing
core/store.py         JSON persistence + next-fire computation
core/ui.py            tkinter main window, dialogs, tray icon
```

Recorded geometry is stored relative to the window:

```json
{ "type": "click", "rect": [0.32, 0.85, 0.45, 0.91], "note": "focus the prompt box" }
{ "type": "type",  "rect": [0.32, 0.85, 0.45, 0.91], "text": "Summarise the open diff.", "clear_first": true }
{ "type": "key",   "combo": "ctrl+enter" }
```

`rect` is `[left, top, right, bottom]` as fractions of the client area, so it is independent of resolution and window position.

## Runtime files

```
data/store.json     sequences, plans and settings
data/logs/*.log     one log file per day
data/shots/*.png    post-run screenshots
```

These are git-ignored — they contain your prompts and schedule.

## Self-tests

```bash
.venv\Scripts\python.exe tests\smoke.py         # core logic + Win32 layer (29 checks)
.venv\Scripts\python.exe tests\integration.py   # real click / CJK input against a scratch window (~5 s of mouse control)
.venv\Scripts\python.exe tests\schedule_e2e.py  # full scheduled run: fire → activate → click → type → send (~8 s of mouse control)
```

`tests/ui_shot.py` and `tests/dialog_shot.py` render the window and dialogs to PNGs in `data/shots/` for layout review.

## Known limitations

1. **A locked screen means a failed run.** If the machine wakes to the lock screen, clicks land on the lock screen. AutoStep detects this and logs `screen is locked` instead of pretending to succeed.
   → For unattended runs, set *Power Options → Require sign-in on wakeup* to **Never**.
2. **Do not touch mouse or keyboard while it runs.** Every step verifies the foreground window, tries to reclaim focus if it was stolen, and aborts (with a log line) if it cannot.
3. **The target window must not be covered** when you record, otherwise the screenshot captures the overlapping window.
4. **The tray process must stay alive.** Quitting stops all schedules.
5. Windows-only by design; the Win32 calls in `core/winsys.py` and `core/executor.py` have no cross-platform fallback.

## License

MIT
