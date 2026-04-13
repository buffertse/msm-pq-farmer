"""
Screen capture with Win32 background capture, ADB fallback, and caching.
"""

import time
import logging
import ctypes
from io import BytesIO
from typing import Optional, Tuple

import numpy as np
from PIL import Image

log = logging.getLogger("msm-pq-farmer")

WINDOW_TITLE = "BlueStacks App Player"
CACHE_TTL = 0.1  # 100 ms


class ScreenCapture:
    """Captures BlueStacks window via Win32 PrintWindow (background) or ADB."""

    def __init__(self, adb_controller=None):
        self.adb = adb_controller
        self.hwnd: Optional[int] = None
        self._cache_img: Optional[np.ndarray] = None
        self._cache_pil: Optional[Image.Image] = None
        self._cache_time: float = 0

    # ── window discovery ───────────────────────────────────────────────

    def find_window(self, title: str = WINDOW_TITLE) -> bool:
        try:
            import win32gui
            results = []

            def cb(hwnd, _):
                t = win32gui.GetWindowText(hwnd)
                if title in t:
                    r = win32gui.GetWindowRect(hwnd)
                    w, h = r[2] - r[0], r[3] - r[1]
                    if w > 200 and h > 200:
                        results.append(hwnd)

            win32gui.EnumWindows(cb, None)
            if results:
                self.hwnd = results[0]
                return True
        except ImportError:
            log.debug("pywin32 not available — using ADB capture")
        return False

    # ── capture ────────────────────────────────────────────────────────

    def capture(self, use_cache: bool = True) -> Optional[np.ndarray]:
        """Return a BGR numpy array of the current screen."""
        now = time.time()
        if use_cache and self._cache_img is not None and (now - self._cache_time) < CACHE_TTL:
            return self._cache_img

        img = self._capture_win32() or self._capture_adb()
        if img is None:
            return None

        arr = np.array(img)[:, :, :3]  # drop alpha if present
        bgr = arr[:, :, ::-1].copy()   # RGB → BGR for OpenCV

        self._cache_img = bgr
        self._cache_pil = img
        self._cache_time = now
        return bgr

    def capture_pil(self, use_cache: bool = True) -> Optional[Image.Image]:
        """Return a PIL RGB image (for legacy pixel sampling)."""
        now = time.time()
        if use_cache and self._cache_pil is not None and (now - self._cache_time) < CACHE_TTL:
            return self._cache_pil

        img = self._capture_win32() or self._capture_adb()
        if img is not None:
            self._cache_pil = img
            self._cache_img = None  # invalidate numpy cache
            self._cache_time = now
        return img

    def capture_region(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        """Capture a sub-region of the screen (BGR)."""
        full = self.capture()
        if full is None:
            return None
        fh, fw = full.shape[:2]
        x1 = max(0, min(x, fw))
        y1 = max(0, min(y, fh))
        x2 = max(0, min(x + w, fw))
        y2 = max(0, min(y + h, fh))
        return full[y1:y2, x1:x2]

    def invalidate_cache(self):
        self._cache_img = None
        self._cache_pil = None
        self._cache_time = 0

    # ── pixel / color helpers ──────────────────────────────────────────

    def get_pixel_color(self, x: int, y: int) -> Optional[Tuple[int, int, int]]:
        """Return (R, G, B) at pixel coordinates."""
        img = self.capture_pil()
        if img is None:
            return None
        w, h = img.size
        px = max(0, min(x, w - 1))
        py = max(0, min(y, h - 1))
        return img.getpixel((px, py))[:3]

    def get_pixel_relative(self, rx: float, ry: float) -> Optional[Tuple[int, int, int]]:
        """Return (R, G, B) at normalised coordinates (0.0-1.0)."""
        img = self.capture_pil()
        if img is None:
            return None
        w, h = img.size
        return img.getpixel((
            max(0, min(int(rx * w), w - 1)),
            max(0, min(int(ry * h), h - 1)),
        ))[:3]

    def get_size(self) -> Optional[Tuple[int, int]]:
        """Return (width, height) of the captured image."""
        img = self.capture_pil(use_cache=True)
        if img is None:
            return None
        return img.size

    def to_grayscale(self, bgr: np.ndarray) -> np.ndarray:
        import cv2
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # ── Win32 PrintWindow (background capture) ─────────────────────────

    def _capture_win32(self) -> Optional[Image.Image]:
        if self.hwnd is None and not self.find_window():
            return None
        try:
            import win32gui
            import win32ui
            from ctypes import windll

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

    # ── ADB fallback capture ───────────────────────────────────────────

    def _capture_adb(self) -> Optional[Image.Image]:
        if self.adb is None:
            return None
        raw = self.adb.screencap()
        if raw is None:
            return None
        try:
            return Image.open(BytesIO(raw)).convert("RGB")
        except Exception as e:
            log.debug("ADB capture decode error: %s", e)
            return None
