# AutoStep

**Record mouse clicks and text input once, then replay them on a schedule — unattended, in the background.**

AutoStep is a small Windows tray application for driving AI desktop apps on a timer. It ships knowing the **Codex** panel inside the ChatGPT desktop app, but the target is configurable: each sequence carries an **app profile** describing how to find that application's window, how to type into it and which key sends. You record a sequence of actions (click a region, type a prompt, press Send), attach that sequence to a schedule, and AutoStep stays quietly in the system tray until the scheduled moment, then performs the whole sequence on the live window.

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
| **App profiles** | Each sequence owns a profile: which window to match, how to type, which key sends. One instance can drive several applications, and switching apps means editing a JSON entry rather than the code. |
| **Text input with CJK support** | Pure-ASCII text is typed key by key; anything containing non-ASCII is pasted through the clipboard (original clipboard content is restored). |
| **Key actions** | `enter`, `ctrl+enter`, `tab`, arrows, and arbitrary `ctrl+shift+x` style combos. |
| **DPI-safe coordinates** | Positions are stored as *percentages of the window's client area*, so moving, resizing or maximising the window never shifts the click. |
| **Multiple sequences** | Keep several action sets, rename them, share one sequence between many schedules. |
| **Three kinds of trigger** | Once; fixed time points that repeat daily or on chosen weekdays; every N hours / days. Several time points in one plan become an ordered daily series. A live summary line in the dialog spells out exactly what the current setting will do. Every plan is re-scheduled automatically after editing. |
| **Sleep-aware** | Arms a waitable timer to wake the system ~90 s before a run, plus a wall-clock catch-up check. |
| **Evidence** | Each run appends to a daily log and can save a screenshot of the final state. |
| **Tray residence** | Closing the window hides it to the tray; optional start-with-Windows via the `Run` registry key. |

## Requirements

- Windows 10 / 11 (relies on Win32 APIs — `pywin32`)
- Python 3.13 (pinned in `mise.toml`; any 3.10+ should work)
- Optional: [mise](https://mise.jdx.dev/) for automatic toolchain setup

Runtime dependencies: `mss`, `Pillow`, `pywin32`, `pyperclip`, `pystray`, `sv-ttk` (about 15 MB total). The UI is plain `tkinter`; the theme comes from `sv-ttk` (Windows 11 look). Without `sv-ttk` the app still runs — it just falls back to the stock system theme.

## Installation

### Option A: download the prebuilt exe (no Python needed)

Grab `AutoStep-*-win64.zip` from [Releases](https://github.com/rightevil/AutoStep/releases), unpack it into any **writable** folder (not `C:\Program Files`), and double-click `AutoStep.exe`.

- Single file, no console window, no Python runtime required;
- On first launch it creates `data/` next to the exe for sequences, plans and logs; if that folder is not writable it falls back to `%APPDATA%\AutoStep`;
- To upgrade, overwrite the exe — `data/` is left untouched.

### Option B: run from source

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

### 2. Pick the app profile

Every sequence carries an **app profile** — the knowledge of how to talk to that one application: how to find its window, how to type into it, and which key sends. That is what lets one instance drive several apps without them interfering.

| Field | Meaning |
|---|---|
| Name | A label, for you |
| Process | Substring match — `ChatGPT` matches `ChatGPT.exe` |
| Title contains (optional) | Disambiguates several windows of the same process |
| Input mode | `auto` (ASCII → keystrokes, non-ASCII → clipboard paste), `keys` (force per-character), `paste` (force clipboard) |
| Clear with Ctrl+A first | Prevents appending to leftover text |
| Send key | `enter` / `ctrl+enter` … used by the **+ Send** action |

- **New profile** — fill the form, or bring the app to the front and pick it from **Pick from window list**; AutoStep writes that window's process name into the current profile.
- **Switch profile** — the dropdown at the top only changes the **currently selected sequence**; other sequences keep their own.
- Profiles live in `data/profiles.json`, plain JSON you can edit, back up or share.

> Upgrading from an older build: the old global target becomes a profile called “原设置” attached to your existing sequences, so nothing has to be re-recorded.

### 3. Record actions

A *sequence* is an ordered list of actions; top-to-bottom is the execution order.

| Button | What it does |
|---|---|
| **+ Click** | Activates the target window, grabs a screenshot of its client area, and overlays a translucent selector. **Drag a box** over the spot to click; release to record. `Esc` or right-click cancels. |
| **+ Type** | Same region selection (pick the input box), then a dialog for the text to send — multi-line and mixed Chinese/English are fine. "Clear with Ctrl+A first" is enabled by default. |
| **+ Send** | Sends the profile's send key (default `enter`). **Do not forget this step** — typing a prompt without sending it does nothing. |
| **+ Key** | Sends an explicit keystroke or combo, e.g. `tab`, `ctrl+a`. |

Reorder with **Up / Down**, tweak an entry with **Edit** (double-click a row), remove with **Delete**. Use **Run once now** to rehearse the sequence immediately; watch the log pane at the bottom.

To add another independent set of actions, use **New** in the sequence row. Rename or delete sequences there too — schedules reference a sequence, so editing a sequence updates every schedule that uses it.

### 4. Create a schedule

Click **+ New plan**: name, trigger, stop condition, and which sequence to run.

Pick one trigger:

| Trigger | How you set it | Behaviour |
|---|---|---|
| **Fixed times** | One or more time points, plus weekdays (none ticked = every day) | Two or more time points become a *time series*: all of them run the same sequence, in order, within the day |
| **Every N hours / days** | A number, a unit, and a start point | Fires at start + k×N. If the machine wakes after several missed cycles, only the most recent one runs — no burst |
| **Once** | A date and a time | Fires once, then the plan is marked *done*. The record is **kept**, and you can re-enable it manually |

Example: time points `09:00`, `13:30`, `21:00` with no weekday ticked → that sequence runs three times a day. Tick Mon/Wed/Fri → it runs three times on those days only.

**Stop condition** (leave empty = unlimited): stop after a date, or after N runs. The plan switches itself off when reached; the record stays.

Other behaviour:

- **Late means skipped**: if a fire could not run (machine off, locked screen, app not running) and it is more than 5 minutes late, AutoStep skips it and waits for the next cycle instead of firing a burst. The log says `missed by N minutes, skipped`.
- Every plan row shows its sequence, trigger, state (`pending` / `done` / `disabled` / `expired`), next fire, and the last result.
- Select a plan and press **Edit** (or double-click) to change anything; saving re-computes the next fire time and re-enables the plan if there is a future one.

### 5. Settings

Settings live in a **tab next to "Execute"** at the top of the window — not a modal dialog, and they no longer take up room on the main page:

| Setting | Meaning |
|---|---|
| Step delay (s) | Fixed pause between two actions. Use **≥ 1.5** for prompts that trigger network work. |
| Wait after activate (s) | Extra settle time after bringing the window to the foreground. |
| Screenshot after run | Saves a PNG to `data/shots/`. |
| Wake system before run | Uses a waitable timer to wake the machine ~90 s early. |
| Minimise to tray on close | Closing the window keeps the scheduler alive in the tray. |
| Start with Windows | Writes a value to `HKCU\...\CurrentVersion\Run`. |
| Dark UI | Requires `sv-ttk`; the checkbox is greyed out without it. |
| Data / log folder | Opens the folder directly — copy the data folder to move machines. |

Every change is saved as you make it: there is **no Save / Cancel**, and switching back to "Execute" picks it up immediately.

Application-specific settings (input mode, clearing, send key) live in **profiles** — the "Target app" row on the main page shows what the current profile uses. Settings only holds rhythm and system behaviour, which is genuinely global.

Once configured, leave AutoStep in the tray. Tray menu: **Show window**, **Run current sequence**, **Quit**.

## How it works

```
main.py               entry point: per-monitor DPI awareness, single-instance mutex, UI start
core/config.py        paths, default settings, app identity (single source for APP_NAME / APP_ID)
core/profile.py       app profiles: window matching / input mode / send key / reserved verify hook
core/winsys.py        window enumeration/activation, coordinate mapping, sleep prevention,
                      waitable-timer wake, lock-screen detection
core/capture.py       client-area screenshot + translucent drag-to-select overlay
core/executor.py      action replay: click / Unicode key-by-key typing / clipboard paste / combos
core/scheduler.py     timer loop, wake arming, plan firing
core/trigger.py       trigger model: parse, next fire time, human-readable summary
core/store.py         JSON persistence + plan scheduling (stop date / run limit)
core/ui/              UI layer, split by class (it used to be one 1500-line file)
core/ui/app.py          main window (Execute tab): step list, schedules, log, tray
core/ui/plan_dialog.py  schedule editor
core/ui/profile_dialog.py  app profile editor
core/ui/calendar_dialog.py month picker
core/ui/prompts.py      single-line / multi-line / key prompts
core/ui/common.py       font constants
core/ui/settings_page.py  Settings tab (execution / system / appearance / folders)
core/ui/theme.py        theme + palette (sv-ttk, matching colors for raw tk widgets)
core/icon.py          icon drawing (shared by tray icon and exe icon)
tools/make_icon.py    generates assets/autostep.ico
AutoStep.spec         PyInstaller build configuration
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
data/profiles.json  app profiles (hand-editable)
data/logs/*.log     one log file per day
data/shots/*.png    post-run screenshots
```

From source these live in the project folder; with the packaged exe they live next to the exe (or in `%APPDATA%\AutoStep` when that folder is read-only — the actual path is written to the first line of the day's log). All of it is git-ignored — it contains your prompts and schedule.

## Self-tests

```bash
.venv\Scripts\python.exe tests\smoke.py         # core logic + profile migration + Win32 layer (45 checks)
.venv\Scripts\python.exe tests\integration.py   # real click / CJK input, incl. a profile-driven pass (~12 s of mouse control)
.venv\Scripts\python.exe tests\schedule_e2e.py  # full scheduled run: fire → activate → click → type → send (~10 s of mouse control)
.venv\Scripts\python.exe tests\ui_settings_tab.py # Settings is a sibling tab, changes save immediately (10 checks)
```

`tests/ui_shot.py`, `tests/ui_profile_shot.py` and `tests/dialog_shot.py` render the window and dialogs to PNGs in `data/shots/` for layout review. `ui_profile_shot.py` uses a throwaway store, so it never touches your real `data/store.json`.

## Known limitations

1. **A locked screen means a failed run.** If the machine wakes to the lock screen, clicks land on the lock screen. AutoStep detects this and logs `screen is locked` instead of pretending to succeed.
   → For unattended runs, set *Power Options → Require sign-in on wakeup* to **Never**.
2. **Do not touch mouse or keyboard while it runs.** Every step verifies the foreground window, tries to reclaim focus if it was stolen, and aborts (with a log line) if it cannot.
3. **The target window must not be covered** when you record, otherwise the screenshot captures the overlapping window.
4. **The tray process must stay alive.** Quitting stops all schedules.
5. Windows-only by design; the Win32 calls in `core/winsys.py` and `core/executor.py` have no cross-platform fallback.

## Building a release

Pushing a `v*` tag builds and publishes everything on GitHub — no local build required:

```bash
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/release.yml` runs on `windows-latest`: install dependencies → compile and import check → PyInstaller with `AutoStep.spec` → zip as `AutoStep-<version>-win64.zip` → create the GitHub Release and attach the zip. The same workflow can be triggered manually from the Actions tab with a version input.

> Hosted runners have no interactive desktop, so `tests/integration.py` and `tests/schedule_e2e.py` (which take over the mouse) are not run in CI — only compile and import checks.

Local build, if you ever need one:

```bash
.venv\Scripts\python.exe -m pip install "pyinstaller>=6.6"
.venv\Scripts\python.exe tools\make_icon.py            # regenerates assets/autostep.ico
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean AutoStep.spec
# output: dist\AutoStep.exe
```

## License

MIT
