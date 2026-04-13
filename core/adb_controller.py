"""
ADB controller — manages the connection to BlueStacks via Android Debug Bridge.
"""

import subprocess
import shutil
import urllib.request
import zipfile
import os
import logging
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("msm-pq-farmer")

ADB_DIR = "platform-tools"
ADB_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
COMMON_PORTS = [5555, 5556, 5565, 5575, 5585, 5595, 5554]


class ADBController:
    """Wraps adb.exe for connecting, tapping, and capturing on BlueStacks."""

    def __init__(self, adb_path: Optional[str] = None, serial: str = "127.0.0.1:5555"):
        self.adb = adb_path or self._find_adb()
        self.serial = serial
        self.connected = False
        self._resolution: Optional[Tuple[int, int]] = None

    # ── locate / download ──────────────────────────────────────────────

    @staticmethod
    def _find_adb() -> Optional[str]:
        candidates = [
            Path(ADB_DIR) / "adb.exe",
            Path("adb.exe"),
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        if shutil.which("adb"):
            return "adb"
        return None

    @staticmethod
    def download_adb() -> Optional[str]:
        zip_path = "platform-tools.zip"
        log.info("Downloading ADB (Android platform-tools)...")
        try:
            def _progress(block, block_size, total):
                done = block * block_size
                if total > 0:
                    pct = min(100, done * 100 // total)
                    bar = "#" * (pct // 3) + "-" * (33 - pct // 3)
                    print(f"\r  [{bar}] {pct}%", end="", flush=True)

            urllib.request.urlretrieve(ADB_URL, zip_path, _progress)
            print()
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(".")
            os.remove(zip_path)
            adb = str(Path(ADB_DIR) / "adb.exe")
            if Path(adb).exists():
                log.info("ADB installed: %s", adb)
                return adb
        except Exception as e:
            log.error("ADB download failed: %s", e)
        return None

    @property
    def available(self) -> bool:
        return self.adb is not None

    # ── connection ─────────────────────────────────────────────────────

    def connect(self, serial: Optional[str] = None) -> bool:
        if serial:
            self.serial = serial
        if not self.adb:
            log.error("ADB executable not found")
            return False
        try:
            self._run(["connect", self.serial])
            r = self._run(["-s", self.serial, "shell", "getprop", "ro.build.version.sdk"])
            if r.stdout.strip():
                self.connected = True
                log.info("ADB connected %s (SDK %s)", self.serial, r.stdout.strip())
                return True
        except Exception as e:
            log.warning("ADB connect failed: %s", e)
        self.connected = False
        return False

    def auto_connect(self) -> bool:
        """Try common BlueStacks ADB ports."""
        if not self.adb:
            return False
        for port in COMMON_PORTS:
            serial = f"127.0.0.1:{port}"
            if self.connect(serial):
                return True
        return False

    def disconnect(self):
        if self.adb and self.connected:
            try:
                self._run(["disconnect", self.serial])
            except Exception:
                pass
        self.connected = False

    # ── commands ───────────────────────────────────────────────────────

    def shell(self, cmd: str, timeout: int = 10) -> str:
        if not self.connected:
            return ""
        try:
            r = self._run(["-s", self.serial, "shell"] + cmd.split(), timeout=timeout)
            return r.stdout.strip()
        except Exception as e:
            log.debug("ADB shell error: %s", e)
            return ""

    def tap(self, x: int, y: int) -> bool:
        return self.shell(f"input tap {x} {y}") is not None

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        return self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}") is not None

    def key_event(self, keycode: int) -> bool:
        return self.shell(f"input keyevent {keycode}") is not None

    def press_back(self) -> bool:
        return self.key_event(4)

    def press_home(self) -> bool:
        return self.key_event(3)

    def press_recent_apps(self) -> bool:
        return self.key_event(187)

    def force_stop(self, package: str) -> bool:
        return self.shell(f"am force-stop {package}") is not None

    def screencap(self) -> Optional[bytes]:
        """Capture screenshot via ADB and return raw PNG bytes."""
        if not self.connected or not self.adb:
            return None
        try:
            r = subprocess.run(
                [self.adb, "-s", self.serial, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=10,
            )
            if r.returncode == 0 and len(r.stdout) > 100:
                return r.stdout
        except Exception as e:
            log.debug("Screencap error: %s", e)
        return None

    def get_resolution(self) -> Optional[Tuple[int, int]]:
        if self._resolution:
            return self._resolution
        out = self.shell("wm size")
        if "x" in out:
            parts = out.split()[-1].split("x")
            try:
                self._resolution = (int(parts[0]), int(parts[1]))
                return self._resolution
            except ValueError:
                pass
        return None

    # ── internal ───────────────────────────────────────────────────────

    def _run(self, args: list, timeout: int = 10) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.adb] + args,
            capture_output=True, text=True, timeout=timeout,
        )
