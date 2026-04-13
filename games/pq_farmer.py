"""
PQ Farmer bot — simple state machine that mirrors the original farmer.py logic.
Works minimized via Win32 PrintWindow + ADB input.
"""

import time
import random
import math
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable

log = logging.getLogger("msm-pq-farmer")


class BotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class GameState(Enum):
    MENU = "menu"
    ACCEPT = "accept"
    WAITING = "waiting"
    UNKNOWN = "unknown"


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
    Simple PQ farmer that follows the exact same logic as the original farmer.py:
      menu → tap Auto Match → wait for Accept → wait in PQ → repeat
    """

    def __init__(self, adb, capture, matcher, inp, config: dict):
        self.adb = adb
        self.capture = capture
        self.matcher = matcher
        self.input = inp
        self.cfg = config

        self.state = BotState.IDLE
        self.game_state = GameState.UNKNOWN
        self.stats = BotStats()
        self.dry_run = False

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

        # Idle tap timer
        interval = self._t("random_tap_interval", [30, 60])
        self._idle_timer = time.time()
        self._idle_interval = random.uniform(*interval)

        # Callbacks for GUI
        self.on_state_change: Optional[Callable] = None
        self.on_stats_update: Optional[Callable] = None

    # ── config helpers ─────────────────────────────────────────────────

    def _t(self, key, default):
        """Get a timings config value."""
        return self.cfg.get("timings", {}).get(key, default)

    def _d(self, key, default):
        """Get a detection config value."""
        return self.cfg.get("detection", {}).get(key, default)

    def _i(self, key, default):
        """Get an input config value."""
        return self.cfg.get("input", {}).get(key, default)

    # ── callbacks ──────────────────────────────────────────────────────

    def _emit_state(self):
        if self.on_state_change:
            try:
                self.on_state_change(self.state.value, self.game_state.value)
            except Exception:
                pass

    def _emit_stats(self):
        if self.on_stats_update:
            try:
                self.on_stats_update(self.stats.to_dict())
            except Exception:
                pass

    # ── state detection (pixel colour, same as original) ───────────────

    @staticmethod
    def _color_match(pixel, target, tol):
        return all(abs(int(a) - int(b)) <= tol for a, b in zip(pixel[:3], target))

    def _detect_state(self) -> GameState:
        """Scan for button colours to determine game state."""
        img = self.capture.capture_pil(use_cache=False)
        if img is None:
            return GameState.UNKNOWN

        w, h = img.size
        ac_match = self._scan_accept(img, w, h)
        am_match = self._scan_auto_match(img, w, h)

        if ac_match and not am_match:
            return GameState.ACCEPT
        if am_match:
            return GameState.MENU
        return GameState.WAITING

    def _scan_auto_match(self, img, w, h) -> bool:
        """Scan bottom-right region for the Auto Match button (yellow-green)."""
        # Auto Match is a large yellow-green button in the bottom-right.
        # Scan rx=0.75-0.96, ry=0.80-0.94
        for rx_pct in range(75, 97, 3):
            for ry_pct in range(80, 95, 2):
                rx = rx_pct / 100.0
                ry = ry_pct / 100.0
                px = img.getpixel((
                    max(0, min(int(rx * w), w - 1)),
                    max(0, min(int(ry * h), h - 1)),
                ))[:3]
                # Yellow-green signature: R>140, G>180, B<80
                if px[0] > 140 and px[1] > 180 and px[2] < 80:
                    return True
        return False

    def _scan_accept(self, img, w, h) -> bool:
        """Scan center region for the Accept button (cyan)."""
        # Accept popup appears in the center of the screen.
        # Scan rx=0.38-0.62, ry=0.50-0.85
        for rx_pct in range(38, 63, 4):
            for ry_pct in range(50, 86, 3):
                rx = rx_pct / 100.0
                ry = ry_pct / 100.0
                px = img.getpixel((
                    max(0, min(int(rx * w), w - 1)),
                    max(0, min(int(ry * h), h - 1)),
                ))[:3]
                # Cyan signature: R<80, G>160, B>160
                if px[0] < 80 and px[1] > 160 and px[2] > 160:
                    return True
        return False

    # ── ADB taps ───────────────────────────────────────────────────────

    def _tap(self, x, y, label=""):
        spread = self._i("tap_spread", 10)
        hx = x + random.randint(-spread, spread)
        hy = y + random.randint(-spread, spread)
        if self.dry_run:
            log.info("[dry] tap (%d,%d) %s", hx, hy, label)
            return
        self.adb.shell(f"input tap {hx} {hy}")
        log.info("Tap (%d,%d) %s", hx, hy, label)

    def _tap_auto_match(self):
        pos = self._i("auto_match_tap", [1700, 950])
        self._tap(pos[0], pos[1], "[Auto Match]")

    def _tap_accept(self):
        pos = self._i("accept_tap", [960, 800])
        self._tap(pos[0], pos[1], "[Accept]")

    def _idle_tap(self):
        """Random tap in safe center area."""
        radius = self._t("random_tap_radius", 200)
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0, radius)
        x = int(960 + dist * math.cos(angle))
        y = int(540 + dist * math.sin(angle))
        if not self.dry_run:
            self.adb.shell(f"input tap {x} {y}")
        log.debug("Idle tap (%d,%d)", x, y)

    def _maybe_idle_tap(self):
        if time.time() - self._idle_timer >= self._idle_interval:
            self._idle_tap()
            self._idle_timer = time.time()
            self._idle_interval = random.uniform(*self._t("random_tap_interval", [30, 60]))

    # ── main loop (tick-based: scan every ~1s, act immediately) ──────────

    def start(self):
        self.state = BotState.RUNNING
        self._stop_event.clear()
        self._pause_event.clear()
        self.stats = BotStats()
        self._emit_state()
        self._emit_stats()
        self._run()

    def start_threaded(self) -> threading.Thread:
        t = threading.Thread(target=self.start, daemon=True, name="pq-farmer")
        t.start()
        return t

    def stop(self):
        log.info("Stopping bot...")
        self._stop_event.set()
        self.state = BotState.STOPPED
        self._emit_state()

    def pause(self):
        if self.state == BotState.RUNNING:
            self._pause_event.set()
            self.state = BotState.PAUSED
            log.info("Bot paused")
            self._emit_state()

    def resume(self):
        if self.state == BotState.PAUSED:
            self._pause_event.clear()
            self.state = BotState.RUNNING
            log.info("Bot resumed")
            self._emit_state()

    def _run(self):
        log.info("MSM PQ Farmer started")

        if self.capture.find_window():
            log.info("BlueStacks window found")
        else:
            log.warning("BlueStacks window not found — using ADB capture")

        if not self.adb.connected:
            if not self.adb.auto_connect():
                log.error("ADB connection failed")
                self.stop()
                return

        max_runs = self.cfg.get("quest", {}).get("max_runs", 0)
        prev_state = None
        in_pq = False
        pq_start = 0
        queue_start = 0
        queued = False

        try:
            while not self._stop_event.is_set():
                if max_runs > 0 and self.stats.pq_runs >= max_runs:
                    log.info("Completed %d runs — stopping", max_runs)
                    break

                if self._pause_event.is_set():
                    time.sleep(1)
                    continue

                state = self._detect_state()
                self.game_state = state
                self._emit_state()

                # Log state transitions
                if state != prev_state:
                    log.info("State: %s", state.value)
                    prev_state = state

                # ── MENU: Auto Match button visible → tap it to queue ──
                if state == GameState.MENU:
                    if in_pq:
                        # PQ just ended, we're back at menu
                        elapsed = int(time.time() - pq_start)
                        log.info("PQ done (%ds)", elapsed)
                        self.stats.pq_runs += 1
                        self._emit_stats()
                        in_pq = False
                        queued = False
                        # Post-reward delay
                        lo, hi = self._t("post_reward_delay", [6, 12])
                        time.sleep(random.uniform(lo, hi))
                        continue

                    if not queued:
                        # Pre-queue delay (human-like)
                        lo, hi = self._t("pre_queue_delay", [0, 20])
                        w = random.uniform(lo, hi)
                        if w > 1:
                            log.info("Queue in %.0fs", w)
                        time.sleep(w)
                        self._tap_auto_match()
                        queued = True
                        queue_start = time.time()
                        time.sleep(random.uniform(1, 3))
                    else:
                        # We tapped Auto Match but still see it →
                        # maybe it didn't register, tap again
                        log.info("Auto Match still visible — retapping")
                        self._tap_auto_match()
                        time.sleep(random.uniform(2, 4))

                # ── ACCEPT: match found → tap Accept ───────────────────
                elif state == GameState.ACCEPT:
                    lo, hi = self._t("accept_reaction_delay", [0.5, 3.0])
                    d = random.uniform(lo, hi)
                    time.sleep(d)
                    log.info("Accept found (reaction %.1fs)", d)
                    self._tap_accept()
                    in_pq = True
                    pq_start = time.time()
                    queued = False
                    time.sleep(random.uniform(1, 2))

                # ── WAITING: in queue, in PQ, or unknown screen ────────
                elif state == GameState.WAITING:
                    if in_pq:
                        # Inside PQ — idle taps to look active
                        self._maybe_idle_tap()
                        # Check for PQ timeout
                        dur = self._t("pq_duration", 350)
                        if time.time() - pq_start > dur:
                            log.info("PQ timeout (%ds)", dur)
                            in_pq = False
                    elif queued:
                        # In matchmaking queue — check for timeout
                        timeout = self._t("matchmaking_timeout", 180)
                        elapsed = int(time.time() - queue_start)
                        if elapsed > 0 and elapsed % 30 == 0:
                            log.info("  Queue: %ds / %ds", elapsed, timeout)
                        if elapsed > timeout:
                            log.warning("Queue timeout (%ds) — retapping Auto Match", timeout)
                            self.stats.queue_timeouts += 1
                            self._emit_stats()
                            queued = False  # will re-tap next tick
                    else:
                        # Neither in PQ nor queued — could be end credits,
                        # loading screen, popup etc. Just wait and rescan.
                        pass

                # ── UNKNOWN: capture failed ─────────────────────────────
                else:
                    pass

                # Poll interval (~1s between scans)
                time.sleep(random.uniform(0.8, 1.5))

        except KeyboardInterrupt:
            pass

        log.info("Bot stopped — %d PQ runs in %.0f minutes",
                 self.stats.pq_runs, self.stats.runtime / 60)
        self.state = BotState.STOPPED
        self._emit_state()
        self._emit_stats()
