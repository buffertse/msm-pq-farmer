"""
Screen capture — uses the exact same Win32 PrintWindow approach as the
original farmer.py. Works in background, even when BlueStacks is minimized.
Falls back to ADB screencap if Win32 is unavailable.
"""

import time
import logging
from io import BytesIO
from typing import Optional, Tuple

log = logging.getLogger("msm-pq-farmer")

WINDOW_TITLE = "BlueStacks App Player"
CACHE_TTL = 0.1


class ScreenCapture:

    def __init__(self, adb_controller=None):
        self.adb = adb_controller
        self.hwnd = None
        self._cache = None
        self._cache_time: float = 0

    # ── window discovery (same as original farmer.py) ──────────────────

    def find_window(self) -> bool:
        try:
            import win32gui
        except ImportError:
            log.debug("pywin32 not available — using ADB capture")
            return False

        results = []

        def cb(hwnd, _):
            t = win32gui.GetWindowText(hwnd)
            if WINDOW_TITLE in t:
                r = win32gui.GetWindowRect(hwnd)
                w, h = r[2] - r[0], r[3] - r[1]
                if w > 200 and h > 200:
                    results.append((hwnd, t, w, h))

        win32gui.EnumWindows(cb, None)
        if results:
            # Pick largest if multiple matches
            results.sort(key=lambda x: x[2] * x[3], reverse=True)
            self.hwnd, title, w, h = results[0]
            log.info("Window: %s (%dx%d)", title, w, h)
            return True
        return False

    # ── capture (same as original farmer.py) ───────────────────────────

    def capture_pil(self, use_cache: bool = True):
        """Return a PIL RGB image. Tries Win32 first, then ADB."""
        now = time.time()
        if use_cache and self._cache is not None and (now - self._cache_time) < CACHE_TTL:
            return self._cache

        img = self._capture_win32() or self._capture_adb()
        if img is not None:
            self._cache = img
            self._cache_time = now
        return img

    def capture(self, use_cache: bool = True):
        """Return a BGR numpy array (for OpenCV). Lazy-imports numpy."""
        img = self.capture_pil(use_cache)
        if img is None:
            return None
        import numpy as np
        arr = np.array(img)[:, :, :3]
        return arr[:, :, ::-1].copy()

    def invalidate_cache(self):
        self._cache = None
        self._cache_time = 0

    def get_size(self) -> Optional[Tuple[int, int]]:
        img = self.capture_pil(use_cache=True)
        return img.size if img else None

    # ── Win32 PrintWindow (exact copy from original farmer.py) ─────────

    def _capture_win32(self):
        if self.hwnd is None:
            return None
        try:
            import win32gui
            import win32ui
            from ctypes import windll
            from PIL import Image

            hwnd = self.hwnd
            minimized = win32gui.IsIconic(hwnd)
            if minimized:
                win32gui.ShowWindow(hwnd, 4)
                time.sleep(0.15)

            r = win32gui.GetWindowRect(hwnd)
            w, h = r[2] - r[0], r[3] - r[1]
            if w < 200 or h < 200:
                return None

            dc = win32gui.GetWindowDC(hwnd)
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
            sdc.DeleteDC()
            mfc.DeleteDC()
            win32gui.ReleaseDC(hwnd, dc)

            if minimized:
                win32gui.ShowWindow(hwnd, 6)
            return img

        except ImportError:
            return None
        except Exception as e:
            log.debug("Win32 capture error: %s", e)
            self.hwnd = None
            return None

    # ── ADB fallback ───────────────────────────────────────────────────

    def _capture_adb(self):
        if self.adb is None:
            return None
        raw = self.adb.screencap()
        if raw is None:
            return None
        try:
            from PIL import Image
            return Image.open(BytesIO(raw)).convert("RGB")
        except Exception as e:
            log.debug("ADB capture decode error: %s", e)
            return None
