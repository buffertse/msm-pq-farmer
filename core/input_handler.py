"""
Human-like input simulation with randomisation for anti-detection.
"""

import math
import random
import time
import logging
from typing import Optional, Tuple

log = logging.getLogger("msm-pq-farmer")


class InputHandler:
    """Sends taps and swipes via ADB with human-like randomisation."""

    def __init__(self, adb_controller, spread: int = 10, screen_w: int = 1920, screen_h: int = 1080):
        self.adb = adb_controller
        self.spread = spread
        self.screen_w = screen_w
        self.screen_h = screen_h

    def _clamp(self, x: int, y: int) -> Tuple[int, int]:
        return max(0, min(x, self.screen_w - 1)), max(0, min(y, self.screen_h - 1))

    def _jitter(self, x: int, y: int, spread: Optional[int] = None) -> Tuple[int, int]:
        s = spread if spread is not None else self.spread
        jx = x + random.randint(-s, s)
        jy = y + random.randint(-s, s)
        return self._clamp(jx, jy)

    def _pre_delay(self):
        time.sleep(random.uniform(0.05, 0.15))

    # ── basic input ────────────────────────────────────────────────────

    def tap(self, x: int, y: int, label: str = "", spread: Optional[int] = None) -> bool:
        self._pre_delay()
        jx, jy = self._jitter(x, y, spread)
        ok = self.adb.tap(jx, jy)
        if label:
            log.info("Tap (%d,%d) %s", jx, jy, label)
        else:
            log.debug("Tap (%d,%d)", jx, jy)
        return ok

    def tap_center(self, match_result, label: str = "") -> bool:
        """Tap at the center of a MatchResult."""
        return self.tap(match_result.cx, match_result.cy, label or f"[{match_result.name}]")

    def double_tap(self, x: int, y: int, label: str = "") -> bool:
        self.tap(x, y, label)
        time.sleep(random.uniform(0.05, 0.12))
        return self.tap(x, y)

    def long_press(self, x: int, y: int, duration_ms: int = 800, label: str = "") -> bool:
        self._pre_delay()
        jx, jy = self._jitter(x, y)
        dur = int(duration_ms * random.uniform(0.9, 1.1))
        log.debug("Long press (%d,%d) %dms %s", jx, jy, dur, label)
        return self.adb.swipe(jx, jy, jx, jy, dur)

    # ── swipe ──────────────────────────────────────────────────────────

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        self._pre_delay()
        jx1, jy1 = self._jitter(x1, y1, 3)
        jx2, jy2 = self._jitter(x2, y2, 3)
        dur = int(duration_ms * random.uniform(0.9, 1.1))
        log.debug("Swipe (%d,%d) -> (%d,%d) %dms", jx1, jy1, jx2, jy2, dur)
        return self.adb.swipe(jx1, jy1, jx2, jy2, dur)

    def swipe_up(self, distance: int = 400, duration_ms: int = 300) -> bool:
        cx, cy = self.screen_w // 2, self.screen_h // 2
        return self.swipe(cx, cy + distance // 2, cx, cy - distance // 2, duration_ms)

    def swipe_down(self, distance: int = 400, duration_ms: int = 300) -> bool:
        cx, cy = self.screen_w // 2, self.screen_h // 2
        return self.swipe(cx, cy - distance // 2, cx, cy + distance // 2, duration_ms)

    def swipe_left(self, distance: int = 400, duration_ms: int = 300) -> bool:
        cx, cy = self.screen_w // 2, self.screen_h // 2
        return self.swipe(cx + distance // 2, cy, cx - distance // 2, cy, duration_ms)

    def swipe_right(self, distance: int = 400, duration_ms: int = 300) -> bool:
        cx, cy = self.screen_w // 2, self.screen_h // 2
        return self.swipe(cx - distance // 2, cy, cx + distance // 2, cy, duration_ms)

    # ── game-specific ──────────────────────────────────────────────────

    def jump(self) -> bool:
        """Double-tap near center to trigger in-game jump."""
        cx, cy = self.screen_w // 2, self.screen_h // 2
        return self.double_tap(cx, cy, "[jump]")

    def random_movement(self) -> bool:
        """Random swipe to look like human activity."""
        cx = random.randint(self.screen_w // 4, 3 * self.screen_w // 4)
        cy = random.randint(self.screen_h // 4, 3 * self.screen_h // 4)
        dx = random.randint(-200, 200)
        dy = random.randint(-100, 100)
        return self.swipe(cx, cy, cx + dx, cy + dy, random.randint(200, 500))

    def random_tap_in_region(self, x: int, y: int, w: int, h: int, label: str = "") -> bool:
        """Tap a random point within the given rectangle."""
        tx = random.randint(x, x + w)
        ty = random.randint(y, y + h)
        return self.tap(tx, ty, label, spread=0)

    def idle_tap(self, center_x: int = 960, center_y: int = 540, radius: int = 200) -> bool:
        """Random tap in the safe center area for idle activity."""
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0, radius)
        x = int(center_x + dist * math.cos(angle))
        y = int(center_y + dist * math.sin(angle))
        log.debug("Idle tap (%d,%d)", x, y)
        return self.adb.tap(x, y)

    # ── sequences ──────────────────────────────────────────────────────

    def tap_sequence(self, points: list, delay: float = 0.3) -> bool:
        """Tap a sequence of (x, y) coordinates with delays."""
        for x, y in points:
            self.tap(x, y)
            time.sleep(delay + random.uniform(-0.05, 0.1))
        return True

    def press_back(self) -> bool:
        self._pre_delay()
        log.debug("Press Back")
        return self.adb.press_back()

    def press_home(self) -> bool:
        self._pre_delay()
        log.debug("Press Home")
        return self.adb.press_home()
