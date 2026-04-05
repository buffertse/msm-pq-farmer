# MapleStory Idle RPG — Party Quest Auto Farmer

Farms Party Quests (Dimensional Crack, First Time Together, etc.) in MapleStory Idle RPG
running on [BlueStacks](https://www.bluestacks.com/). Runs in the background —
BlueStacks doesn't need to be focused or even visible on screen.

## Features

- **Background operation** — captures the BlueStacks window via Win32 API, no need to keep it in the foreground
- **ADB input** — sends taps through Android Debug Bridge, works with the window minimised
- **Anti-detection** — randomised coordinates, human-like reaction times, variable delays, idle taps during PQ
- **Auto-calibration** — detects button colours and positions on first run
- **Zero manual config** — setup wizard walks through everything, downloads ADB automatically if needed
- **Configurable** — all timings, colours, and coordinates in a single `config.json`

## Requirements

- Windows 10 or 11
- [Python 3.10+](https://python.org) (or install from the Microsoft Store)
- [BlueStacks 5](https://www.bluestacks.com/)
- MapleStory Idle RPG (installed inside BlueStacks)

## Quick Start

1. **Download or clone** this repository
2. **Double-click `start.bat`**

That's it. On first run the setup wizard will:

- Download ADB if you don't have it
- Find and connect to BlueStacks
- Test that taps are working
- Calibrate button colours for your screen

After setup, just navigate to the Party Quest menu in the game and let it run.

## Usage

```
start.bat                        # normal start
start.bat --dry-run              # test mode, no actual taps
start.bat --max-runs 50          # stop after 50 PQ runs
start.bat --recalibrate          # redo the setup wizard
start.bat --serial 127.0.0.1:5565  # custom ADB port
```

Or run directly:

```
python farmer.py [options]
```

## Configuration

After the first run, settings are saved to `config.json`. You can edit this
file to fine-tune behaviour:

| Setting | What it does | Default |
|---------|-------------|---------|
| `adb_serial` | BlueStacks ADB address | `127.0.0.1:5555` |
| `auto_match_tap` | Auto Match button coordinates | `[1700, 950]` |
| `accept_tap` | Accept button coordinates | `[960, 800]` |
| `auto_match_color` | Expected RGB colour of Auto Match | `[187, 221, 34]` |
| `accept_color` | Expected RGB colour of Accept | `[32, 187, 205]` |
| `pq_duration` | Max seconds to wait inside a PQ | `350` |
| `matchmaking_timeout` | Max seconds to wait in queue | `180` |
| `pre_queue_delay` | Random delay before queueing `[min, max]` | `[0, 20]` |
| `tap_spread` | Random pixel offset on every tap | `10` |
| `accept_reaction_delay` | Delay before tapping Accept `[min, max]` | `[0.5, 3.0]` |

Delete `config.json` and restart to run the setup wizard again.

## How It Works

1. **Capture** the BlueStacks window using `PrintWindow` (Win32) — works even when
   the window is behind other windows or minimised
2. **Sample pixel colours** at known button positions to determine the current state
   (PQ menu / matchmaking / Accept popup / in-game)
3. **Send taps** via `adb shell input tap` with randomised offsets
4. **Loop**: queue → accept → wait for PQ to finish → collect rewards → repeat

## Troubleshooting

**"BlueStacks not found"** — Make sure BlueStacks is running and not fully closed to the system tray.

**"ADB connection failed"** — Open BlueStacks Settings → Advanced → enable "Android Debug Bridge (ADB)". Restart BlueStacks.

**Buttons not detected** — Run with `--recalibrate` to redo colour calibration. Different screen resolutions and DPI settings affect the captured colours.

**"Python is not installed"** — Install Python from [python.org](https://python.org) or the Microsoft Store (search "Python 3.12").

## Project Structure

```
msm-pq-farmer/
├── farmer.py           # everything in one file
├── config.json         # generated on first run
├── start.bat           # double-click launcher
├── requirements.txt
├── LICENSE
└── README.md
```

## Disclaimer

This project is provided for educational purposes only. Automating gameplay
may violate Nexon's Terms of Service for MapleStory Idle RPG. Use entirely at your
own risk. The author takes no responsibility for any consequences including
account suspension.

## License

[MIT](LICENSE)
