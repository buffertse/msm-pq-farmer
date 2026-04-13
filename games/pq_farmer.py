"""
PQ Farmer — based directly on the original farmer.py PQFarmer class.
Same pixel detection, same state machine, same wait loops.
Added: auto-calibration, GUI callbacks, pause/resume, recovery.
"""

import time
import random
import math
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

log = logging.getLogger("msm-pq-farmer")

DEFAULTS = {
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
}


@dataclass
class BotStats:
    pq_runs: int = 0
    queue_timeouts: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def runtime(self) -> float:
        return time.time() - self.start_time

    @property
    def avg_pq_time(self) -> float:
        return self.runtime / self.pq_runs if self.pq_runs else 0

    @property
    def success_rate(self) -> float:
        total = self.pq_runs + self.queue_timeouts
        return (self.pq_runs / total) * 100 if total else 0

    def to_dict(self) -> dict:
        return {
            "pq_runs": self.pq_runs,
            "queue_timeouts": self.queue_timeouts,
            "runtime": self.runtime,
            "avg_pq_time": self.avg_pq_time,
            "success_rate": self.success_rate,
        }


class PQFarmer:
    """
    Exact same logic as original farmer.py PQFarmer, with added:
    - Auto-calibration on first capture
    - GUI callbacks (on_state_change, on_stats_update)
    - Pause / resume / stop
    - Soft recovery (tap center to dismiss popups)
    """

    def __init__(self, adb, capture, cfg: dict):
        self.adb = adb
        self.capture = capture
        self.cfg = self._merge_defaults(cfg)
        self.dry_run = False

        self.stats = BotStats()
        self._state_str = "idle"
        self._game_state = "unknown"
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._rt = time.time()
        self._rti = random.uniform(*self.cfg["random_tap_interval"])
        self._calibrated = self.cfg.get("calibrated", False)

        # GUI callbacks
        self.on_state_change: Optional[Callable] = None
        self.on_stats_update: Optional[Callable] = None

    @staticmethod
    def _merge_defaults(cfg: dict) -> dict:
        """Flatten nested config and merge with defaults."""
        flat = dict(DEFAULTS)
        # Support both flat (original) and nested (new) config
        if "detection" in cfg:
            for k, v in cfg["detection"].items():
                flat[k] = v
        if "input" in cfg:
            for k, v in cfg["input"].items():
                flat[k] = v
        if "timings" in cfg:
            for k, v in cfg["timings"].items():
                flat[k] = v
        # Flat keys override
        for k in DEFAULTS:
            if k in cfg:
                flat[k] = cfg[k]
        if "adb" in cfg and "serial" in cfg["adb"]:
            flat["adb_serial"] = cfg["adb"]["serial"]
        elif "adb_serial" in cfg:
            flat["adb_serial"] = cfg["adb_serial"]
        else:
            flat["adb_serial"] = "127.0.0.1:5555"
        # max_runs
        if "quest" in cfg:
            flat["max_runs"] = cfg["quest"].get("max_runs", 0)
        elif "max_runs" not in flat:
            flat["max_runs"] = 0
        return flat

    def _emit(self):
        if self.on_state_change:
            try:
                self.on_state_change(self._state_str, self._game_state)
            except Exception:
                pass
        if self.on_stats_update:
            try:
                self.on_stats_update(self.stats.to_dict())
            except Exception:
                pass

    # ── capture + colour detection (exact copy from original) ──────────

    def _cap(self):
        """Capture window — retries find_window every time (like original)."""
        if self.capture.hwnd is None:
            self.capture.find_window()
        try:
            return self.capture.capture_pil(use_cache=False)
        except Exception as e:
            log.debug("Capture error: %s", e)
            self.capture.hwnd = None
            return None

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

    # ── auto-calibration (from original setup_wizard) ──────────────────

    def _calibrate(self, img):
        """Scan the captured image to find button positions and colours."""
        s = img.size
        log.info("Calibrating on %dx%d capture...", s[0], s[1])

        # Scan for Auto Match (yellow-green, bottom-right)
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
            self.cfg["auto_match_check"] = [round(rx, 3), round(ry, 3)]
            self.cfg["auto_match_color"] = list(colour)
            # Derive tap position from relative coords
            self.cfg["auto_match_tap"] = [int(rx * s[0]), int(ry * s[1])]
            log.info("Auto Match at (%.2f, %.2f) RGB(%d,%d,%d)",
                     rx, ry, *colour)
        else:
            log.info("Auto Match not found — using defaults")

        # Scan for Accept (cyan, center column)
        best_ac = None
        best_ac_score = 0
        for ry in [i / 100 for i in range(55, 80)]:
            px = img.getpixel((int(0.46 * s[0]), int(ry * s[1])))[:3]
            if px[1] > 160 and px[2] > 160 and px[0] < 80:
                score = px[1] + px[2] - px[0]
                if score > best_ac_score:
                    best_ac_score = score
                    best_ac = (0.46, ry, px)

        if best_ac:
            rx, ry, colour = best_ac
            self.cfg["accept_check"] = [round(rx, 3), round(ry, 3)]
            self.cfg["accept_color"] = list(colour)
            self.cfg["accept_tap"] = [int(rx * s[0]), int(ry * s[1])]
            log.info("Accept at (%.2f, %.2f) RGB(%d,%d,%d)",
                     rx, ry, *colour)
        else:
            log.info("Accept not visible — will calibrate when it appears")

        self._calibrated = True

    # ── ADB commands ───────────────────────────────────────────────────

    def _shell(self, cmd):
        return self.adb.shell(cmd)

    def _tap(self, x, y, label=""):
        s = self.cfg["tap_spread"]
        hx, hy = x + random.randint(-s, s), y + random.randint(-s, s)
        if self.dry_run:
            log.info("[dry] tap (%d,%d) %s", hx, hy, label)
            return
        self._shell(f"input tap {hx} {hy}")
        log.info("Tap (%d,%d) %s", hx, hy, label)

    def _idle_tap(self):
        r = self.cfg["random_tap_radius"]
        a, d = random.uniform(0, 2 * math.pi), random.uniform(0, r)
        x, y = int(960 + d * math.cos(a)), int(540 + d * math.sin(a))
        if not self.dry_run:
            self._shell(f"input tap {x} {y}")
        log.debug("Idle tap (%d,%d)", x, y)

    def _maybe_idle_tap(self):
        if time.time() - self._rt >= self._rti:
            self._idle_tap()
            self._rt = time.time()
            self._rti = random.uniform(*self.cfg["random_tap_interval"])

    # ── recovery ───────────────────────────────────────────────────────

    def _soft_recovery(self):
        """Tap center to dismiss popups, then check state."""
        log.warning("Soft recovery — tapping center to dismiss popups")
        self._tap(960, 540, "[recovery]")
        time.sleep(2)

    # ── wait loops (exact copy from original) ──────────────────────────

    def _wait_accept(self):
        log.info("Waiting for Accept...")
        t0 = time.time()
        timeout = self.cfg["matchmaking_timeout"]
        poll = self.cfg["accept_poll_interval"]

        while not self._stop.is_set() and time.time() - t0 < timeout:
            if self._pause.is_set():
                time.sleep(1)
                continue

            s = self._state()
            self._game_state = s
            self._emit()

            if s == "accept":
                # Try to calibrate accept position if not yet done
                if not self._calibrated:
                    img = self._cap()
                    if img:
                        self._calibrate(img)

                lo, hi = self.cfg["accept_reaction_delay"]
                d = random.uniform(lo, hi)
                time.sleep(d)
                log.info("Accept found (reaction %.1fs)", d)
                self._tap(*self.cfg["accept_tap"], "[Accept]")
                time.sleep(1.5)
                if self._state() != "accept":
                    return True
                time.sleep(random.uniform(0.3, 1))
                self._tap(*self.cfg["accept_tap"], "[Accept retry]")
                return True

            if s == "menu":
                log.info("Back at menu (match failed)")
                return False

            e = int(time.time() - t0)
            if e > 0 and e % 30 == 0:
                log.info("  Queue: %ds / %ds", e, timeout)
            time.sleep(poll + random.uniform(0, 0.5))

        log.warning("Queue timeout (%ds)", timeout)
        self.stats.queue_timeouts += 1
        return False

    def _wait_pq(self):
        dur = self.cfg["pq_duration"]
        log.info("In PQ (timeout %ds)", dur)
        self._game_state = "in_pq"
        self._emit()
        t0 = time.time()

        while not self._stop.is_set() and time.time() - t0 < dur:
            if self._pause.is_set():
                time.sleep(1)
                continue

            self._maybe_idle_tap()
            s = self._state()
            if s == "menu":
                log.info("PQ done (%ds)", int(time.time() - t0))
                return
            if s == "accept":
                time.sleep(random.uniform(0.5, 2))
                self._tap(*self.cfg["accept_tap"], "[Accept]")
            self._emit()
            time.sleep(random.uniform(4, 7))

        log.info("PQ timeout — continuing")

    # ── main loop (exact same flow as original) ────────────────────────

    def start(self):
        self._state_str = "running"
        self._stop.clear()
        self._pause.clear()
        self.stats = BotStats()
        self._emit()
        self._run()

    def start_threaded(self) -> threading.Thread:
        t = threading.Thread(target=self.start, daemon=True, name="pq-farmer")
        t.start()
        return t

    def stop(self):
        log.info("Stopping...")
        self._stop.set()
        self._state_str = "stopped"
        self._emit()

    def pause(self):
        self._pause.set()
        self._state_str = "paused"
        log.info("Paused")
        self._emit()

    def resume(self):
        self._pause.clear()
        self._state_str = "running"
        log.info("Resumed")
        self._emit()

    @property
    def state(self):
        class _S:
            def __init__(s2): s2.value = self._state_str
        return _S()

    def _run(self):
        log.info("MSM PQ Farmer started")

        # Find window (non-fatal — retries on each capture)
        if self.capture.find_window():
            log.info("BlueStacks window found")
        else:
            log.warning("BlueStacks window not found — will retry")

        if not self.adb.connected:
            if not self.adb.auto_connect():
                log.error("ADB connection failed")
                self.stop()
                return

        # First capture + auto-calibrate
        img = self._cap()
        if img:
            log.info("Capture: %dx%d", img.size[0], img.size[1])
            if not self._calibrated:
                self._calibrate(img)
        else:
            log.warning("Cannot capture window")

        state = self._state()
        self._game_state = state
        log.info("State: %s", state)
        log.info("Running")
        self._emit()

        max_runs = self.cfg.get("max_runs", 0)
        stuck_count = 0

        try:
            while not self._stop.is_set():
                if 0 < max_runs <= self.stats.pq_runs:
                    log.info("Finished %d runs", max_runs)
                    break

                if self._pause.is_set():
                    time.sleep(1)
                    continue

                self.stats.pq_runs  # trigger runtime update
                self._emit()

                state = self._state()
                self._game_state = state
                log.info("--- run %d --- [%s]", self.stats.pq_runs + 1, state)

                if state == "menu":
                    stuck_count = 0
                    lo, hi = self.cfg["pre_queue_delay"]
                    w = random.uniform(lo, hi)
                    log.info("Queue in %.0fs", w)
                    time.sleep(w)
                    self._tap(*self.cfg["auto_match_tap"], "[Auto Match]")
                    time.sleep(random.uniform(2, 4))
                    if self._wait_accept():
                        self._wait_pq()
                        lo, hi = self.cfg["post_reward_delay"]
                        time.sleep(random.uniform(lo, hi))
                        self.stats.pq_runs += 1
                        self._emit()
                    else:
                        time.sleep(random.uniform(2, 5))

                elif state == "accept":
                    stuck_count = 0
                    time.sleep(random.uniform(0.5, 2.5))
                    self._tap(*self.cfg["accept_tap"], "[Accept]")
                    time.sleep(2)
                    self._wait_pq()
                    lo, hi = self.cfg["post_reward_delay"]
                    time.sleep(random.uniform(lo, hi))
                    self.stats.pq_runs += 1
                    self._emit()

                elif state == "waiting":
                    stuck_count += 1
                    log.info("In queue or PQ")
                    if stuck_count > 3:
                        self._soft_recovery()
                        stuck_count = 0
                    if self._wait_accept():
                        self._wait_pq()
                        lo, hi = self.cfg["post_reward_delay"]
                        time.sleep(random.uniform(lo, hi))
                        self.stats.pq_runs += 1
                        self._emit()
                    else:
                        lo, hi = self.cfg["pre_queue_delay"]
                        time.sleep(random.uniform(lo, hi))
                        self._tap(*self.cfg["auto_match_tap"], "[Auto Match]")
                        time.sleep(random.uniform(2, 4))
                else:
                    stuck_count += 1
                    if stuck_count > 3:
                        self._soft_recovery()
                        stuck_count = 0
                    time.sleep(5)

        except KeyboardInterrupt:
            pass

        log.info("Stopped — %d PQ runs in %.0f minutes",
                 self.stats.pq_runs, self.stats.runtime / 60)
        self._state_str = "stopped"
        self._emit()
