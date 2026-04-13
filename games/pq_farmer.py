"""
PQ Farmer bot — state machine with template matching, escalating recovery,
multi-quest support, and callback hooks for the GUI.
"""

import time
import random
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, List

from core.screen_capture import ScreenCapture
from core.template_matcher import TemplateMatcher, MatchResult
from core.input_handler import InputHandler
from core.adb_controller import ADBController

log = logging.getLogger("msm-pq-farmer")


class BotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class GameState(Enum):
    MENU = "menu"
    ACCEPT = "accept"
    QUEUED = "queued"
    IN_PQ = "in_pq"
    LOADING = "loading"
    UNKNOWN = "unknown"


class QuestType(Enum):
    SLEEPYWOOD = "sleepywood"
    LUDIBRIUM = "ludibrium"
    ORBIS = "orbis"
    ZAKUM = "zakum"


# Template names per quest for wave detection
WAVE_TEMPLATES = {
    QuestType.SLEEPYWOOD: {
        1: "sleepywood_wave1",
        2: "sleepywood_wave2",
        3: "sleepywood_wave3",
    },
    QuestType.LUDIBRIUM: {
        1: "ludibrium_wave1",
        2: "ludibrium_wave2",
        3: "ludibrium_wave3",
    },
    QuestType.ORBIS: {
        1: "orbis_wave1",
        2: "orbis_wave2",
        3: "orbis_wave3",
    },
    QuestType.ZAKUM: {
        1: "zakum_wave1",
        2: "zakum_wave2",
        3: "zakum_wave3",
    },
}

# Templates used for state detection
STATE_TEMPLATES = {
    "auto_match": "auto_match_btn",
    "accept": "accept_btn",
    "loading": "loading_screen",
    "in_pq": "pq_indicator",
}

# Templates for recovery
RECOVERY_TEMPLATES = [
    "lost_connection",
    "event_popup",
    "exit_btn",
    "ok_btn",
    "close_btn",
    "party_screen",
    "menu_btn",
]


@dataclass
class BotStats:
    pq_runs: int = 0
    queue_timeouts: int = 0
    consecutive_timeouts: int = 0
    soft_recoveries: int = 0
    hard_recoveries: int = 0
    restarts: int = 0
    start_time: float = field(default_factory=time.time)
    current_wave: int = 0
    last_pq_duration: float = 0

    @property
    def runtime(self) -> float:
        return time.time() - self.start_time

    @property
    def avg_pq_time(self) -> float:
        if self.pq_runs == 0:
            return 0
        return self.runtime / self.pq_runs

    @property
    def success_rate(self) -> float:
        total = self.pq_runs + self.queue_timeouts
        if total == 0:
            return 0
        return (self.pq_runs / total) * 100

    def to_dict(self) -> dict:
        return {
            "pq_runs": self.pq_runs,
            "queue_timeouts": self.queue_timeouts,
            "soft_recoveries": self.soft_recoveries,
            "hard_recoveries": self.hard_recoveries,
            "restarts": self.restarts,
            "runtime": self.runtime,
            "avg_pq_time": self.avg_pq_time,
            "success_rate": self.success_rate,
            "current_wave": self.current_wave,
        }


class PQFarmer:
    """Main bot class with state machine, recovery, and GUI callbacks."""

    def __init__(
        self,
        adb: ADBController,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        inp: InputHandler,
        config: dict,
        quest_type: QuestType = QuestType.SLEEPYWOOD,
    ):
        self.adb = adb
        self.capture = capture
        self.matcher = matcher
        self.input = inp
        self.cfg = config
        self.quest_type = quest_type

        self.state = BotState.IDLE
        self.game_state = GameState.UNKNOWN
        self.stats = BotStats()
        self.dry_run = False
        self._use_templates = False
        self._last_activity = time.time()
        self._idle_timer = time.time()
        self._idle_interval = 0
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

        # Callbacks for GUI
        self.on_state_change: Optional[Callable] = None
        self.on_stats_update: Optional[Callable] = None
        self.on_log: Optional[Callable] = None

        self._detect_templates()
        self._reset_idle_timer()

    def _detect_templates(self):
        """Check if template images are available."""
        templates = self.matcher.list_templates()
        required = ["auto_match_btn", "accept_btn"]
        self._use_templates = all(t in templates for t in required)
        if self._use_templates:
            log.info("Template matching enabled (%d templates)", len(templates))
            self.matcher.preload(templates)
        else:
            log.info("Using pixel color detection (no templates found)")

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

    # ── state detection ────────────────────────────────────────────────

    def _detect_state(self) -> GameState:
        """Determine the current game state."""
        screen = self.capture.capture(use_cache=False)
        if screen is None:
            return GameState.UNKNOWN

        if self._use_templates:
            return self._detect_state_template(screen)
        return self._detect_state_pixel()

    def _detect_state_template(self, screen) -> GameState:
        """State detection via template matching."""
        # Check accept first (higher priority)
        if self.matcher.find(screen, "accept_btn"):
            return GameState.ACCEPT

        if self.matcher.find(screen, "auto_match_btn"):
            return GameState.MENU

        if self.matcher.find(screen, "loading_screen"):
            return GameState.LOADING

        pq_templates = ["pq_indicator"] + [
            f"{self.quest_type.value}_wave{w}" for w in (1, 2, 3)
        ]
        if self.matcher.find_any(screen, pq_templates):
            return GameState.IN_PQ

        return GameState.QUEUED

    def _detect_state_pixel(self) -> GameState:
        """Legacy state detection via pixel colour sampling."""
        det = self.cfg.get("detection", {})
        img = self.capture.capture_pil(use_cache=False)
        if img is None:
            return GameState.UNKNOWN

        w, h = img.size
        am_rx, am_ry = det.get("auto_match_check", [0.88, 0.86])
        am_color = det.get("auto_match_color", [187, 221, 34])
        am_tol = det.get("auto_match_tolerance", 45)

        ac_rx, ac_ry = det.get("accept_check", [0.46, 0.70])
        ac_color = det.get("accept_color", [32, 187, 205])
        ac_tol = det.get("accept_tolerance", 40)

        am_px = img.getpixel((
            max(0, min(int(am_rx * w), w - 1)),
            max(0, min(int(am_ry * h), h - 1)),
        ))[:3]
        ac_px = img.getpixel((
            max(0, min(int(ac_rx * w), w - 1)),
            max(0, min(int(ac_ry * h), h - 1)),
        ))[:3]

        am_match = self.matcher.color_match(am_px, am_color, am_tol)
        ac_match = self.matcher.color_match(ac_px, ac_color, ac_tol)

        if ac_match and not am_match:
            return GameState.ACCEPT
        if am_match:
            return GameState.MENU
        return GameState.QUEUED

    # ── wave detection ─────────────────────────────────────────────────

    def _detect_wave(self, screen) -> int:
        if not self._use_templates:
            return 0
        waves = WAVE_TEMPLATES.get(self.quest_type, {})
        for wave_num in (3, 2, 1):
            tmpl_name = waves.get(wave_num)
            if tmpl_name and self.matcher.find(screen, tmpl_name):
                return wave_num
        return 0

    def _check_boss_alert(self, screen) -> bool:
        if not self._use_templates:
            return False
        return self.matcher.find(screen, "boss_alert") is not None

    # ── recovery ───────────────────────────────────────────────────────

    def _soft_recovery(self) -> bool:
        """Tier 1: Scan for known popups and try to dismiss them."""
        log.warning("Soft recovery — scanning for popups")
        self.stats.soft_recoveries += 1
        screen = self.capture.capture(use_cache=False)
        if screen is None:
            return False

        if self._use_templates:
            for tmpl in RECOVERY_TEMPLATES:
                m = self.matcher.find(screen, tmpl)
                if m:
                    log.info("Recovery: found %s, tapping", tmpl)
                    self.input.tap_center(m, f"[recovery:{tmpl}]")
                    time.sleep(1.5)
                    self._last_activity = time.time()
                    return True

        # Fallback: tap center to dismiss possible dialogs
        self.input.tap(960, 540, "[recovery:center]")
        time.sleep(1)
        self._last_activity = time.time()
        return True

    def _hard_recovery(self) -> bool:
        """Tier 2: Navigate back and try to restart from menu."""
        log.warning("Hard recovery — restarting navigation")
        self.stats.hard_recoveries += 1
        for _ in range(5):
            self.input.press_back()
            time.sleep(0.8)
        time.sleep(2)
        self.input.press_home()
        time.sleep(3)
        self._last_activity = time.time()
        return True

    def _hard_reset(self) -> bool:
        """Tier 3: Force-stop and restart the app."""
        log.warning("Hard reset — force-stopping app")
        self.stats.restarts += 1
        package = self.cfg.get("recovery", {}).get("app_package", "com.nexon.msm.global")

        self.adb.press_recent_apps()
        time.sleep(1)
        screen = self.capture.capture(use_cache=False)
        if screen is not None and self._use_templates:
            m = self.matcher.find(screen, "clear_all")
            if m:
                self.input.tap_center(m, "[clear_all]")
                time.sleep(1)

        self.adb.force_stop(package)
        time.sleep(2)
        self.adb.press_home()
        time.sleep(3)

        # Relaunch via monkey
        self.adb.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
        time.sleep(15)
        self._last_activity = time.time()
        return True

    def _check_stuck(self) -> bool:
        """Check if we're stuck and trigger recovery."""
        recovery_cfg = self.cfg.get("recovery", {})
        if not recovery_cfg.get("enabled", True):
            return False

        idle = time.time() - self._last_activity
        soft = recovery_cfg.get("soft_timeout", 120)
        hard = recovery_cfg.get("hard_timeout", 300)

        if idle > hard:
            return self._hard_reset()
        if idle > soft:
            return self._soft_recovery()
        return False

    # ── idle taps ──────────────────────────────────────────────────────

    def _reset_idle_timer(self):
        self._idle_timer = time.time()
        interval = self.cfg.get("timings", {}).get("random_tap_interval", [30, 60])
        self._idle_interval = random.uniform(*interval)

    def _maybe_idle_tap(self):
        if time.time() - self._idle_timer >= self._idle_interval:
            radius = self.cfg.get("timings", {}).get("random_tap_radius", 200)
            if not self.dry_run:
                self.input.idle_tap(radius=radius)
            self._reset_idle_timer()

    # ── action helpers ─────────────────────────────────────────────────

    def _tap_auto_match(self):
        if self._use_templates:
            screen = self.capture.capture(use_cache=False)
            if screen is not None:
                m = self.matcher.find(screen, "auto_match_btn")
                if m:
                    if not self.dry_run:
                        self.input.tap_center(m, "[Auto Match]")
                    else:
                        log.info("[dry] Tap Auto Match at (%d,%d)", m.cx, m.cy)
                    return
        # Fallback to configured coordinates
        tap = self.cfg.get("input", {}).get("auto_match_tap", [1700, 950])
        if not self.dry_run:
            self.input.tap(tap[0], tap[1], "[Auto Match]")
        else:
            log.info("[dry] Tap Auto Match at (%d,%d)", tap[0], tap[1])

    def _tap_accept(self):
        if self._use_templates:
            screen = self.capture.capture(use_cache=False)
            if screen is not None:
                m = self.matcher.find(screen, "accept_btn")
                if m:
                    if not self.dry_run:
                        self.input.tap_center(m, "[Accept]")
                    else:
                        log.info("[dry] Tap Accept at (%d,%d)", m.cx, m.cy)
                    return
        tap = self.cfg.get("input", {}).get("accept_tap", [960, 800])
        if not self.dry_run:
            self.input.tap(tap[0], tap[1], "[Accept]")
        else:
            log.info("[dry] Tap Accept at (%d,%d)", tap[0], tap[1])

    # ── wait phases ────────────────────────────────────────────────────

    def _wait_accept(self) -> bool:
        """Wait for the Accept popup during matchmaking."""
        log.info("Waiting for Accept...")
        timings = self.cfg.get("timings", {})
        timeout = timings.get("matchmaking_timeout", 180)
        poll = timings.get("accept_poll_interval", 0.8)
        t0 = time.time()

        while not self._stop_event.is_set() and time.time() - t0 < timeout:
            if self._pause_event.is_set():
                time.sleep(1)
                continue

            state = self._detect_state()
            self.game_state = state
            self._emit_state()

            if state == GameState.ACCEPT:
                delay = timings.get("accept_reaction_delay", [0.5, 3.0])
                d = random.uniform(*delay)
                time.sleep(d)
                log.info("Accept found (reaction %.1fs)", d)
                self._tap_accept()
                time.sleep(1.5)

                if self._detect_state() != GameState.ACCEPT:
                    self._last_activity = time.time()
                    return True
                time.sleep(random.uniform(0.3, 1))
                self._tap_accept()
                self._last_activity = time.time()
                return True

            if state == GameState.MENU:
                log.info("Back at menu (match failed)")
                return False

            elapsed = int(time.time() - t0)
            if elapsed > 0 and elapsed % 30 == 0:
                log.info("  Queue: %ds / %ds", elapsed, timeout)

            time.sleep(poll + random.uniform(0, 0.5))

        log.warning("Queue timeout (%ds)", timeout)
        self.stats.queue_timeouts += 1
        self.stats.consecutive_timeouts += 1
        self._emit_stats()

        max_ct = self.cfg.get("recovery", {}).get("max_queue_timeouts", 3)
        if self.stats.consecutive_timeouts >= max_ct:
            log.warning("Too many consecutive timeouts (%d) — restarting", max_ct)
            self._hard_reset()
            self.stats.consecutive_timeouts = 0
        return False

    def _wait_pq(self):
        """Wait inside PQ with idle taps and wave tracking."""
        timings = self.cfg.get("timings", {})
        dur = timings.get("pq_duration", 350)
        log.info("In PQ (timeout %ds)", dur)
        self.game_state = GameState.IN_PQ
        self._emit_state()
        t0 = time.time()

        while not self._stop_event.is_set() and time.time() - t0 < dur:
            if self._pause_event.is_set():
                time.sleep(1)
                continue

            self._maybe_idle_tap()

            screen = self.capture.capture(use_cache=False)
            if screen is not None:
                wave = self._detect_wave(screen)
                if wave > 0 and wave != self.stats.current_wave:
                    self.stats.current_wave = wave
                    log.info("Wave %d detected", wave)
                    self._emit_stats()

                if wave == 3 and self._check_boss_alert(screen):
                    log.info("Boss alert! Dodging...")
                    if not self.dry_run:
                        self.input.jump()

            state = self._detect_state()
            if state == GameState.MENU:
                elapsed = int(time.time() - t0)
                log.info("PQ done (%ds)", elapsed)
                self.stats.last_pq_duration = elapsed
                self._last_activity = time.time()
                return
            if state == GameState.ACCEPT:
                time.sleep(random.uniform(0.5, 2))
                self._tap_accept()

            time.sleep(random.uniform(4, 7))

        log.info("PQ timeout — continuing")
        self._last_activity = time.time()

    # ── main loop ──────────────────────────────────────────────────────

    def start(self):
        """Start the bot in the current thread."""
        self.state = BotState.RUNNING
        self._stop_event.clear()
        self._pause_event.clear()
        self.stats = BotStats()
        self._last_activity = time.time()
        self._emit_state()
        self._emit_stats()
        self.run()

    def start_threaded(self) -> threading.Thread:
        """Start the bot in a daemon thread."""
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

    def run(self):
        log.info("MSM PQ Farmer started")
        log.info("Quest: %s | Templates: %s", self.quest_type.value,
                 "enabled" if self._use_templates else "pixel fallback")

        if not self.capture.find_window():
            log.warning("BlueStacks window not found")

        if not self.adb.connected:
            if not self.adb.auto_connect():
                log.error("ADB connection failed")
                self.stop()
                return

        max_runs = self.cfg.get("quest", {}).get("max_runs", 0)

        try:
            while not self._stop_event.is_set():
                if max_runs > 0 and self.stats.pq_runs >= max_runs:
                    log.info("Completed %d runs — stopping", max_runs)
                    break

                if self._pause_event.is_set():
                    time.sleep(1)
                    continue

                self._check_stuck()

                state = self._detect_state()
                self.game_state = state
                self._emit_state()
                run_num = self.stats.pq_runs + 1
                log.info("--- run %d --- [%s]", run_num, state.value)

                timings = self.cfg.get("timings", {})

                if state == GameState.MENU:
                    delay = timings.get("pre_queue_delay", [0, 20])
                    w = random.uniform(*delay)
                    log.info("Queue in %.0fs", w)
                    time.sleep(w)
                    self._tap_auto_match()
                    time.sleep(random.uniform(2, 4))
                    if self._wait_accept():
                        self.stats.consecutive_timeouts = 0
                        self._wait_pq()
                        reward = timings.get("post_reward_delay", [6, 12])
                        time.sleep(random.uniform(*reward))
                        self.stats.pq_runs += 1
                        self.stats.current_wave = 0
                        self._emit_stats()
                    else:
                        time.sleep(random.uniform(2, 5))

                elif state == GameState.ACCEPT:
                    delay = timings.get("accept_reaction_delay", [0.5, 3.0])
                    time.sleep(random.uniform(*delay))
                    self._tap_accept()
                    time.sleep(2)
                    self._wait_pq()
                    reward = timings.get("post_reward_delay", [6, 12])
                    time.sleep(random.uniform(*reward))
                    self.stats.pq_runs += 1
                    self.stats.current_wave = 0
                    self._emit_stats()

                elif state in (GameState.QUEUED, GameState.LOADING):
                    self._last_activity = time.time()
                    if self._wait_accept():
                        self.stats.consecutive_timeouts = 0
                        self._wait_pq()
                        reward = timings.get("post_reward_delay", [6, 12])
                        time.sleep(random.uniform(*reward))
                        self.stats.pq_runs += 1
                        self.stats.current_wave = 0
                        self._emit_stats()
                    else:
                        delay = timings.get("pre_queue_delay", [0, 20])
                        time.sleep(random.uniform(*delay))
                        self._tap_auto_match()
                        time.sleep(random.uniform(2, 4))

                elif state == GameState.IN_PQ:
                    self._last_activity = time.time()
                    self._wait_pq()
                    reward = timings.get("post_reward_delay", [6, 12])
                    time.sleep(random.uniform(*reward))
                    self.stats.pq_runs += 1
                    self.stats.current_wave = 0
                    self._emit_stats()

                else:
                    time.sleep(5)

        except KeyboardInterrupt:
            pass

        log.info("Bot stopped — %d PQ runs in %.0f minutes",
                 self.stats.pq_runs, self.stats.runtime / 60)
        self.state = BotState.STOPPED
        self._emit_state()
        self._emit_stats()
