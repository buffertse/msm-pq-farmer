"""
Logging system with colored console output, file rotation, and GUI callbacks.
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List


class LogCallback:
    """Manages log callbacks for GUI integration."""

    def __init__(self):
        self._callbacks: List[Callable] = []

    def add(self, callback: Callable):
        self._callbacks.append(callback)

    def remove(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, level: str, message: str, timestamp: str):
        for cb in list(self._callbacks):
            try:
                cb(level, message, timestamp)
            except Exception:
                pass


LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):

    def format(self, record):
        color = LEVEL_COLORS.get(record.levelname, RESET)
        record.levelname_colored = f"{color}{record.levelname:<8}{RESET}"
        return super().format(record)


class CallbackHandler(logging.Handler):
    """Forwards log records to registered callbacks (used by the GUI)."""

    def __init__(self, log_callback: LogCallback):
        super().__init__()
        self.log_callback = log_callback

    def emit(self, record):
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        self.log_callback.emit(record.levelname, self.format(record), ts)


class DuplicateFilter(logging.Filter):
    """Suppresses identical consecutive messages."""

    def __init__(self):
        super().__init__()
        self._last = None
        self._count = 0

    def filter(self, record):
        msg = record.getMessage()
        if msg == self._last:
            self._count += 1
            return False
        if self._count > 0:
            self._last = None
            self._count = 0
        self._last = msg
        return True


def setup_logger(
    name: str = "msm-pq-farmer",
    log_dir: str = "logs",
    max_files: int = 5,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_callback: Optional[LogCallback] = None,
    enable_duplicate_filter: bool = True,
) -> logging.Logger:
    """Create and configure the application logger."""

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.filters.clear()

    if enable_duplicate_filter:
        logger.addFilter(DuplicateFilter())

    # Enable ANSI colors on Windows
    if sys.platform == "win32":
        os.system("")

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    fmt = ColoredFormatter(
        "%(asctime)s %(levelname_colored)s %(message)s", datefmt="%H:%M:%S"
    )
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler with rotation
    try:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)

        existing = sorted(log_path.glob("bot_*.log"), key=lambda p: p.stat().st_mtime)
        while len(existing) >= max_files:
            existing.pop(0).unlink()

        filename = f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        fh = logging.FileHandler(log_path / filename, encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(fh)
    except Exception:
        pass

    # GUI callback handler
    if log_callback:
        ch = CallbackHandler(log_callback)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    return logger
