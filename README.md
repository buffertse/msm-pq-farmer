# MapleStory Idle RPG — Party Quest Auto Farmer

Farms Party Quests (Sleepywood, Ludibrium, Orbis, Zakum) in MapleStory Idle RPG
running on [BlueStacks](https://www.bluestacks.com/). Runs in the background —
BlueStacks doesn't need to be focused or even visible on screen.

## Features

- **Modern GUI** — dark-themed dashboard with real-time stats, log viewer, and settings panel
- **Background operation** — captures the BlueStacks window via Win32 API, no need to keep it in the foreground
- **Template matching** — OpenCV-based image detection with confidence thresholds (falls back to pixel colour sampling when no templates are available)
- **Multi-quest support** — Sleepywood, Ludibrium, Orbis, and Zakum with wave tracking
- **Escalating recovery** — 3-tier stuck detection: soft popup dismiss → app restart → hard reset
- **ADB input** — sends taps through Android Debug Bridge, works with the window minimised
- **Anti-detection** — randomised coordinates, human-like reaction times, variable delays, idle taps during PQ
- **Proper logging** — coloured console output + timestamped log files with automatic rotation
- **YAML config** — dot-notation access, recursive merge with defaults, auto-migration from legacy config.json
- **Template creator** — interactive tool to capture template images from the live emulator
- **Zero manual config** — everything is auto-detected on first run
- **CLI mode** — run headless from the command line with `--cli`

## Requirements

- Windows 10 or 11
- [Python 3.10+](https://python.org) (or install from the Microsoft Store)
- [BlueStacks 5](https://www.bluestacks.com/)
- MapleStory Idle RPG (installed inside BlueStacks)

## Quick Start

1. **Download or clone** this repository
2. **Double-click `start.bat`**

That's it. The launcher will:

- Install all required Python packages automatically
- Download ADB if you don't have it
- Find and connect to BlueStacks
- Open the GUI where you click **Start** to begin farming

## Usage

### GUI (default)

```
start.bat
```

The GUI provides:
- **Dashboard** — live PQ count, runtime, average time, and success rate
- **Settings** — quest selection, timing adjustments, anti-detection tuning
- **Log** — full scrollable log with colour-coded entries
- Start / Pause / Stop controls

### CLI

```
start_cli.bat                          # headless mode
start_cli.bat --quest ludibrium        # specific quest
start_cli.bat --max-runs 50            # stop after 50 runs
start_cli.bat --dry-run                # test mode, no taps
start_cli.bat --serial 127.0.0.1:5565  # custom ADB port
```

### Template Creator

To improve detection accuracy, capture template images from your game:

```
python -m tools.template_creator
```

Controls:
- **Left-click + drag** to select a region
- **Right-click** to tap in-game (navigate menus)
- **C** to capture a fresh screenshot
- **S** to save the selection as a template
- **Q** to quit

## Configuration

Settings are stored in `settings.yaml` (auto-created on first save). You can edit it
directly or use the GUI settings panel. See `config/settings.yaml.example` for all options.

| Setting | What it does | Default |
|---------|-------------|---------|
| `adb.serial` | BlueStacks ADB address | `127.0.0.1:5555` |
| `quest.type` | Which PQ to farm | `sleepywood` |
| `quest.max_runs` | Stop after N runs (0 = unlimited) | `0` |
| `detection.method` | `auto` / `template` / `pixel` | `auto` |
| `detection.confidence` | Template match threshold | `0.85` |
| `timings.pq_duration` | Max seconds inside a PQ | `350` |
| `timings.matchmaking_timeout` | Max seconds in queue | `180` |
| `input.tap_spread` | Random pixel offset on every tap | `10` |
| `recovery.enabled` | Auto-recover from stuck states | `true` |
| `recovery.soft_timeout` | Seconds before soft recovery | `120` |
| `recovery.hard_timeout` | Seconds before hard reset | `300` |

Legacy `config.json` files are automatically migrated to the new format.

## How It Works

1. **Capture** the BlueStacks window using `PrintWindow` (Win32) — works in the background
2. **Detect state** using OpenCV template matching (or pixel colour sampling as fallback)
3. **Send taps** via `adb shell input tap` with randomised offsets and human-like delays
4. **Recover** from stuck states with escalating recovery (popup dismiss → restart → force-stop)
5. **Loop**: queue → accept → wait for PQ → collect rewards → repeat

## Project Structure

```
msm-pq-farmer/
├── main.py                  # entry point (GUI + CLI)
├── config.py                # YAML config manager
├── farmer.py                # legacy single-file version
├── start.bat                # double-click launcher (GUI)
├── start_cli.bat            # CLI launcher
├── requirements.txt
├── core/
│   ├── adb_controller.py    # ADB connection and commands
│   ├── screen_capture.py    # Win32 + ADB screenshot with caching
│   ├── template_matcher.py  # OpenCV template matching engine
│   ├── input_handler.py     # human-like tap/swipe simulation
│   └── logger.py            # coloured logging with file rotation
├── games/
│   └── pq_farmer.py         # bot state machine with recovery
├── gui/
│   ├── app.py               # main application window
│   ├── pages.py             # dashboard, settings, log pages
│   ├── widgets.py           # custom UI components
│   └── theme.py             # colours and fonts
├── tools/
│   └── template_creator.py  # interactive template capture
├── templates/               # template images for matching
├── config/
│   └── settings.yaml.example
└── logs/                    # auto-rotated log files
```

## Troubleshooting

**"Python hittas inte"** — Install Python from [python.org](https://python.org) or the Microsoft Store. Make sure to check "Add Python to PATH" during installation.

**"Kunde inte ansluta"** — Make sure BlueStacks is running. Open BlueStacks Settings → Advanced → enable "Android Debug Bridge (ADB)". Restart BlueStacks.

**Buttons not detected** — Use the Template Creator to capture template images from your game for more accurate detection.

**GUI looks wrong** — Make sure you have Windows 10 or 11. The GUI uses native Tkinter with a custom dark theme.

## Disclaimer

This project is provided for educational purposes only. Automating gameplay
may violate Nexon's Terms of Service for MapleStory Idle RPG. Use entirely at your
own risk. The author takes no responsibility for any consequences including
account suspension.

## License

[MIT](LICENSE)
