"""
msm-pq-farmer — MapleStory Idle RPG Party Quest auto-farmer for BlueStacks.
https://github.com/INSERT/msm-pq-farmer
"""

import subprocess, time, sys, os, argparse, random, math, ctypes, json, zipfile
import urllib.request, shutil
from pathlib import Path
from PIL import Image
import win32gui, win32ui
from ctypes import windll

ctypes.windll.user32.SetProcessDPIAware()

VERSION      = "1.0.0"
CONFIG_FILE  = "config.json"
ADB_DIR      = "platform-tools"
ADB_URL      = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
WINDOW_TITLE = "BlueStacks App Player"

# ── defaults ────────────────────────────────────────────────────────────────

DEFAULTS = {
    "adb_serial":             "127.0.0.1:5555",
    "auto_match_tap":         [1700, 950],
    "accept_tap":             [960, 800],
    "auto_match_check":       [0.88, 0.86],
    "auto_match_color":       [187, 221, 34],
    "auto_match_tolerance":   45,
    "accept_check":           [0.46, 0.70],
    "accept_color":           [32, 187, 205],
    "accept_tolerance":       40,
    "pq_duration":            350,
    "matchmaking_timeout":    180,
    "accept_poll_interval":   0.8,
    "pre_queue_delay":        [0, 20],
    "post_reward_delay":      [6, 12],
    "tap_spread":             10,
    "random_tap_interval":    [30, 60],
    "random_tap_radius":      200,
    "accept_reaction_delay":  [0.5, 3.0],
    "calibrated":             False,
}

# ── helpers ─────────────────────────────────────────────────────────────────

def ts():
    return time.strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}")

def save_config(cfg, path=CONFIG_FILE):
    with open(path, "w") as f:
        json.dump(cfg, f, indent=4)

def load_config(path=CONFIG_FILE):
    cfg = dict(DEFAULTS)
    if Path(path).exists():
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg

# ── ADB management ──────────────────────────────────────────────────────────

def find_adb():
    """Look for adb.exe in common locations."""
    candidates = [
        Path(ADB_DIR) / "adb.exe",
        Path("adb.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # check PATH
    if shutil.which("adb"):
        return "adb"
    return None

def download_adb():
    """Download Android platform-tools (contains adb.exe)."""
    zip_path = "platform-tools.zip"
    print()
    print("  Downloading ADB (Android platform-tools)...")
    print(f"  Source: {ADB_URL}")
    print()
    try:
        urllib.request.urlretrieve(ADB_URL, zip_path, _download_progress)
        print()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(".")
        os.remove(zip_path)
        adb = str(Path(ADB_DIR) / "adb.exe")
        if Path(adb).exists():
            print(f"  ADB installed: {adb}")
            return adb
    except Exception as e:
        print(f"  Download failed: {e}")
        print("  Download manually from https://developer.android.com/tools/releases/platform-tools")
    return None

def _download_progress(block, block_size, total):
    done = block * block_size
    if total > 0:
        pct = min(100, done * 100 // total)
        bar = "#" * (pct // 3) + "-" * (33 - pct // 3)
        print(f"\r  [{bar}] {pct}%", end="", flush=True)

# ── window capture ──────────────────────────────────────────────────────────

def find_window(title=WINDOW_TITLE):
    results = []
    def cb(hwnd, _):
        t = win32gui.GetWindowText(hwnd)
        if title in t:
            r = win32gui.GetWindowRect(hwnd)
            w, h = r[2] - r[0], r[3] - r[1]
            if w > 200 and h > 200:
                results.append((hwnd, t, w, h))
    win32gui.EnumWindows(cb, None)
    return results[0] if results else None

def capture_window(hwnd):
    """Capture window content via PrintWindow. Works in background."""
    minimized = win32gui.IsIconic(hwnd)
    if minimized:
        win32gui.ShowWindow(hwnd, 4)
        time.sleep(0.15)

    r = win32gui.GetWindowRect(hwnd)
    w, h = r[2] - r[0], r[3] - r[1]
    if w < 200 or h < 200:
        return None

    dc  = win32gui.GetWindowDC(hwnd)
    mfc = win32ui.CreateDCFromHandle(dc)
    sdc = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc, w, h)
    sdc.SelectObject(bmp)

    ok = windll.user32.PrintWindow(hwnd, sdc.GetSafeHdc(), 3)
    if not ok:
        windll.user32.PrintWindow(hwnd, sdc.GetSafeHdc(), 0)

    info = bmp.GetInfo()
    img = Image.frombuffer(
        "RGB", (info["bmWidth"], info["bmHeight"]),
        bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1,
    )

    win32gui.DeleteObject(bmp.GetHandle())
    sdc.DeleteDC(); mfc.DeleteDC()
    win32gui.ReleaseDC(hwnd, dc)

    if minimized:
        win32gui.ShowWindow(hwnd, 6)
    return img

# ── setup wizard ────────────────────────────────────────────────────────────

def setup_wizard(adb_path):
    """Interactive first-time setup. Returns (adb_path, config)."""
    cfg = dict(DEFAULTS)

    print()
    print("=" * 56)
    print("  MapleStory Idle RPG PQ Farmer - First Time Setup")
    print("=" * 56)
    print()

    # step 1: BlueStacks
    print("  [1/4] Looking for BlueStacks...")
    win = find_window()
    if not win:
        print()
        print("  BlueStacks is not running or the window is not visible.")
        print("  Start BlueStacks, open MapleStory Idle RPG, then run this again.")
        sys.exit(1)
    hwnd, title, ww, wh = win
    print(f"         Found: {title} ({ww}x{wh})")

    # step 2: ADB
    print()
    print("  [2/4] Connecting to BlueStacks...")

    # try common BlueStacks ADB ports
    connected = False
    ports = [5555, 5556, 5565, 5575, 5585, 5595, 5554]
    for port in ports:
        serial = f"127.0.0.1:{port}"
        subprocess.run([adb_path, "connect", serial],
                       capture_output=True, timeout=5)
        r = subprocess.run(
            [adb_path, "-s", serial, "shell",
             "getprop", "ro.build.version.sdk"],
            capture_output=True, text=True, timeout=5,
        )
        if r.stdout.strip():
            cfg["adb_serial"] = serial
            print(f"         Connected on port {port} (SDK {r.stdout.strip()})")
            connected = True
            break

    if not connected:
        print()
        print("  Could not connect to BlueStacks.")
        print("  Make sure ADB is enabled:")
        print("    BlueStacks > Settings > Advanced > Android Debug Bridge")
        print("  Then restart BlueStacks and try again.")
        sys.exit(1)

    # step 3: verify tap works
    print()
    print("  [3/4] Verifying input...")
    r = subprocess.run(
        [adb_path, "-s", cfg["adb_serial"], "shell", "input", "tap", "960", "540"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0 or "error" in r.stderr.lower():
        print("  ADB tap failed. BlueStacks may be blocking input.")
        print("  Make sure ADB is enabled in BlueStacks settings.")
        sys.exit(1)
    print("         Input working")

    # step 4: calibrate
    print()
    print("  [4/4] Calibrating...")
    print("         Open MapleStory Idle RPG and go to:")
    print("         Party Quest > Dimensional Crack (Easy)")
    print("         The Auto Match button should be visible.")
    input("         Press Enter when ready...")

    img = capture_window(hwnd)
    if img is None:
        print("  Could not capture the window.")
        print("  Make sure BlueStacks is not minimised and try again.")
        sys.exit(1)

    s = img.size
    print(f"         Window: {s[0]}x{s[1]}")

    # scan for Auto Match button (yellow-green, bottom-right region)
    best_am = None
    best_score = 0
    for rx in [i / 100 for i in range(80, 96)]:
        for ry in [i / 100 for i in range(80, 92)]:
            px = img.getpixel((int(rx * s[0]), int(ry * s[1])))[:3]
            if px[1] > 180 and px[0] > 140 and px[2] < 80:
                score = px[1] + px[0] - px[2]
                if score > best_score:
                    best_score = score
                    best_am = (rx, ry, px)

    if best_am:
        rx, ry, colour = best_am
        cfg["auto_match_check"] = [round(rx, 3), round(ry, 3)]
        cfg["auto_match_color"] = list(colour)
        print(f"         Found Auto Match at ({rx:.2f}, {ry:.2f})")
    else:
        print("         Auto Match button not detected — using defaults.")
        print("         You can recalibrate later with --recalibrate")

    # Accept button — try to calibrate automatically by queueing
    print()
    print("         Calibrating Accept button...")
    print("         Queueing for a match — this may take a moment.")

    # tap Auto Match to start queueing
    subprocess.run(
        [adb_path, "-s", cfg["adb_serial"], "shell",
         "input", "tap", str(cfg["auto_match_tap"][0]), str(cfg["auto_match_tap"][1])],
        capture_output=True, timeout=10,
    )

    # poll for Accept popup (up to 90 seconds)
    accept_found = False
    print("         Waiting for Accept popup", end="", flush=True)
    for _ in range(45):
        time.sleep(2)
        print(".", end="", flush=True)
        img2 = capture_window(hwnd)
        if img2 is None:
            continue

        best_ac = None
        best_ac_score = 0
        for ry in [i / 100 for i in range(55, 80)]:
            px = img2.getpixel((int(0.46 * s[0]), int(ry * s[1])))[:3]
            if px[1] > 160 and px[2] > 160 and px[0] < 80:
                score = px[1] + px[2] - px[0]
                if score > best_ac_score:
                    best_ac_score = score
                    best_ac = (0.46, ry, px)

        if best_ac:
            rx, ry, colour = best_ac
            cfg["accept_check"] = [round(rx, 3), round(ry, 3)]
            cfg["accept_color"] = list(colour)
            print()
            print(f"         Found Accept at ({rx:.2f}, {ry:.2f})")
            # accept the match so we don't waste it
            subprocess.run(
                [adb_path, "-s", cfg["adb_serial"], "shell",
                 "input", "tap", str(cfg["accept_tap"][0]), str(cfg["accept_tap"][1])],
                capture_output=True, timeout=10,
            )
            accept_found = True
            break

    if not accept_found:
        print()
        print("         No match found within 90s — using default Accept colours.")
        print("         This is usually fine. Recalibrate later if needed.")

    cfg["calibrated"] = True
    save_config(cfg)
    print()
    print(f"  Settings saved to {CONFIG_FILE}")
    print()
    print("  Setup complete!")
    print()
    return cfg


# ── farmer ──────────────────────────────────────────────────────────────────

class PQFarmer:
    def __init__(self, adb_path, cfg, dry_run=False, max_runs=0):
        self.adb   = adb_path
        self.cfg   = cfg
        self.dry   = dry_run
        self.max   = max_runs
        self.runs  = 0
        self.hwnd  = None
        self._rt   = time.time()
        self._rti  = random.uniform(*cfg["random_tap_interval"])

    # ── logging ────────────────────────────────────────────────────────

    def _log(self, msg):
        print(f"[{ts()}] {msg}")

    # ── window ─────────────────────────────────────────────────────────

    def _find(self):
        win = find_window()
        if win:
            self.hwnd = win[0]
            return True
        return False

    def _cap(self):
        if not self.hwnd and not self._find():
            self._log("Window not found")
            return None
        try:
            return capture_window(self.hwnd)
        except Exception as e:
            self._log(f"Capture error: {e}")
            self.hwnd = None
            return None

    # ── colour detection ───────────────────────────────────────────────

    def _sample(self, img, rx, ry):
        w, h = img.size
        return img.getpixel((
            max(0, min(int(rx * w), w - 1)),
            max(0, min(int(ry * h), h - 1)),
        ))[:3]

    def _match(self, px, target, tol):
        return all(abs(a - b) <= tol for a, b in zip(px[:3], target))

    def _state(self):
        img = self._cap()
        if img is None:
            return "unknown"
        c = self.cfg
        am = self._match(
            self._sample(img, *c["auto_match_check"]),
            c["auto_match_color"], c["auto_match_tolerance"],
        )
        ac = self._match(
            self._sample(img, *c["accept_check"]),
            c["accept_color"], c["accept_tolerance"],
        )
        if ac and not am:
            return "accept"
        if am:
            return "menu"
        return "waiting"

    # ── ADB ────────────────────────────────────────────────────────────

    def _shell(self, cmd):
        try:
            return subprocess.run(
                [self.adb, "-s", self.cfg["adb_serial"], "shell"] + cmd.split(),
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except Exception as e:
            self._log(f"ADB: {e}")
            return ""

    def _tap(self, x, y, label=""):
        s = self.cfg["tap_spread"]
        hx, hy = x + random.randint(-s, s), y + random.randint(-s, s)
        if self.dry:
            self._log(f"[dry] tap ({hx},{hy}) {label}")
            return
        self._shell(f"input tap {hx} {hy}")
        self._log(f"Tap ({hx},{hy}) {label}")

    def _idle_tap(self):
        """Random tap in the safe center area."""
        r = self.cfg["random_tap_radius"]
        a, d = random.uniform(0, 2 * math.pi), random.uniform(0, r)
        x, y = int(960 + d * math.cos(a)), int(540 + d * math.sin(a))
        if not self.dry:
            self._shell(f"input tap {x} {y}")
        self._log(f"Idle tap ({x},{y})")

    def _maybe_idle_tap(self):
        if time.time() - self._rt >= self._rti:
            self._idle_tap()
            self._rt = time.time()
            self._rti = random.uniform(*self.cfg["random_tap_interval"])

    # ── wait loops ─────────────────────────────────────────────────────

    def _wait_accept(self):
        self._log("Waiting for Accept...")
        t0 = time.time()
        timeout = self.cfg["matchmaking_timeout"]
        poll = self.cfg["accept_poll_interval"]

        while time.time() - t0 < timeout:
            s = self._state()
            if s == "accept":
                lo, hi = self.cfg["accept_reaction_delay"]
                d = random.uniform(lo, hi)
                time.sleep(d)
                self._log(f"Accept found (reaction {d:.1f}s)")
                self._tap(*self.cfg["accept_tap"], "[Accept]")
                time.sleep(1.5)
                if self._state() != "accept":
                    return True
                time.sleep(random.uniform(0.3, 1))
                self._tap(*self.cfg["accept_tap"], "[Accept retry]")
                return True
            if s == "menu":
                self._log("Back at menu (match failed)")
                return False
            e = int(time.time() - t0)
            if e > 0 and e % 30 == 0:
                self._log(f"  Queue: {e}s")
            time.sleep(poll + random.uniform(0, 0.5))

        self._log(f"Queue timeout ({timeout}s)")
        return False

    def _wait_pq(self):
        dur = self.cfg["pq_duration"]
        self._log(f"In PQ (timeout {dur}s)")
        t0 = time.time()
        while time.time() - t0 < dur:
            self._maybe_idle_tap()
            s = self._state()
            if s == "menu":
                self._log(f"PQ done ({int(time.time()-t0)}s)")
                return
            if s == "accept":
                time.sleep(random.uniform(0.5, 2))
                self._tap(*self.cfg["accept_tap"], "[Accept]")
            time.sleep(random.uniform(4, 7))
        self._log("PQ timeout — continuing")

    # ── main ───────────────────────────────────────────────────────────

    def _connect(self):
        serial = self.cfg["adb_serial"]
        self._log(f"ADB connect {serial}")
        subprocess.run([self.adb, "connect", serial],
                       capture_output=True, timeout=10)
        r = subprocess.run(
            [self.adb, "-s", serial, "shell",
             "getprop", "ro.build.version.sdk"],
            capture_output=True, text=True, timeout=10,
        )
        ok = bool(r.stdout.strip())
        if ok:
            self._log(f"ADB ready (SDK {r.stdout.strip()})")
        else:
            self._log("ADB connection failed")
        return ok

    def run(self):
        print()
        self._log(f"MapleStory Idle RPG PQ Farmer v{VERSION}")
        self._log("=" * 44)

        if not self._find():
            self._log("BlueStacks not found — is it running?")
            return
        if not self._connect():
            self._log("Enable ADB: BlueStacks > Settings > Advanced")
            return

        img = self._cap()
        if not img:
            self._log("Cannot capture window")
            return
        self._log(f"Capture: {img.size[0]}x{img.size[1]}")
        self._log(f"State: {self._state()}")
        self._log("Running (Ctrl+C to stop)")
        print()

        try:
            while True:
                if 0 < self.max <= self.runs:
                    self._log(f"Finished {self.max} runs")
                    break

                self.runs += 1
                self._log(f"--- run {self.runs} ---")
                state = self._state()
                self._log(f"State: {state}")

                if state == "menu":
                    lo, hi = self.cfg["pre_queue_delay"]
                    w = random.uniform(lo, hi)
                    self._log(f"Queue in {w:.0f}s")
                    time.sleep(w)
                    self._tap(*self.cfg["auto_match_tap"], "[Auto Match]")
                    time.sleep(random.uniform(2, 4))
                    if self._wait_accept():
                        self._wait_pq()
                        lo, hi = self.cfg["post_reward_delay"]
                        time.sleep(random.uniform(lo, hi))
                    else:
                        time.sleep(random.uniform(2, 5))

                elif state == "accept":
                    time.sleep(random.uniform(0.5, 2.5))
                    self._tap(*self.cfg["accept_tap"], "[Accept]")
                    time.sleep(2)
                    self._wait_pq()
                    lo, hi = self.cfg["post_reward_delay"]
                    time.sleep(random.uniform(lo, hi))

                elif state == "waiting":
                    self._log("In queue or PQ")
                    if self._wait_accept():
                        self._wait_pq()
                        lo, hi = self.cfg["post_reward_delay"]
                        time.sleep(random.uniform(lo, hi))
                    else:
                        lo, hi = self.cfg["pre_queue_delay"]
                        time.sleep(random.uniform(lo, hi))
                        self._tap(*self.cfg["auto_match_tap"], "[Auto Match]")
                        time.sleep(random.uniform(2, 4))
                else:
                    time.sleep(5)

        except KeyboardInterrupt:
            print()
            self._log(f"Stopped after {self.runs} runs")

        self._log("Done")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="farmer",
        description="MapleStory Idle RPG Party Quest auto-farmer for BlueStacks",
    )
    ap.add_argument("-n", "--max-runs", type=int, default=0,
                    metavar="N", help="stop after N runs (0 = unlimited)")
    ap.add_argument("--dry-run", action="store_true",
                    help="detect states but don't tap")
    ap.add_argument("--recalibrate", action="store_true",
                    help="re-run the setup wizard")
    ap.add_argument("--adb", default=None, metavar="PATH",
                    help="path to adb.exe")
    ap.add_argument("--serial", default=None, metavar="ADDR",
                    help="ADB device address (default 127.0.0.1:5555)")
    ap.add_argument("--config", default=CONFIG_FILE, metavar="FILE",
                    help="config file (default config.json)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args()

    # find or download ADB
    adb = args.adb or find_adb()
    if not adb:
        print()
        print("  ADB (Android Debug Bridge) not found.")
        dl = input("  Download it automatically? [Y/n]: ").strip().lower()
        if dl in ("n", "no"):
            print("  Download from https://developer.android.com/tools/releases/platform-tools")
            print("  and place adb.exe next to this script, or pass --adb <path>")
            sys.exit(1)
        adb = download_adb()
        if not adb:
            sys.exit(1)

    # load or create config
    cfg = load_config(args.config)
    if args.serial:
        cfg["adb_serial"] = args.serial

    if not cfg.get("calibrated") or args.recalibrate:
        cfg = setup_wizard(adb)

    PQFarmer(adb, cfg, dry_run=args.dry_run, max_runs=args.max_runs).run()


if __name__ == "__main__":
    main()
