"""
Configuration manager with YAML support, dot-notation access, and defaults merging.
"""

import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("msm-pq-farmer")

DEFAULTS = {
    "adb": {
        "serial": "127.0.0.1:5555",
        "path": None,
    },
    "capture": {
        "method": "auto",  # auto | win32 | adb
        "cache_ttl": 0.1,
    },
    "quest": {
        "type": "sleepywood",  # sleepywood | ludibrium | orbis | zakum
        "max_runs": 0,
    },
    "detection": {
        "method": "auto",  # auto | template | pixel
        "confidence": 0.85,
        "auto_match_check": [0.88, 0.86],
        "auto_match_color": [187, 221, 34],
        "auto_match_tolerance": 45,
        "accept_check": [0.46, 0.70],
        "accept_color": [32, 187, 205],
        "accept_tolerance": 40,
    },
    "input": {
        "auto_match_tap": [1700, 950],
        "accept_tap": [960, 800],
        "tap_spread": 10,
    },
    "timings": {
        "pq_duration": 350,
        "matchmaking_timeout": 180,
        "accept_poll_interval": 0.8,
        "pre_queue_delay": [0, 20],
        "post_reward_delay": [6, 12],
        "accept_reaction_delay": [0.5, 3.0],
        "random_tap_interval": [30, 60],
        "random_tap_radius": 200,
    },
    "recovery": {
        "enabled": True,
        "soft_timeout": 120,
        "hard_timeout": 300,
        "max_queue_timeouts": 3,
        "app_package": "com.nexon.msm.global",
    },
    "logging": {
        "console_level": "INFO",
        "file_level": "DEBUG",
        "max_log_files": 5,
    },
    "gui": {
        "theme": "dark",
        "window_width": 1100,
        "window_height": 720,
    },
    "calibrated": False,
}

CONFIG_FILE = "settings.yaml"
LEGACY_CONFIG = "config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (base is not mutated)."""
    merged = dict(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


class ConfigManager:
    """YAML-based configuration with dot-notation access and defaults merge."""

    def __init__(self, path: Optional[str] = None):
        self._path = Path(path) if path else self._find_config()
        self._data = dict(DEFAULTS)
        self.load()

    def _find_config(self) -> Path:
        if Path(CONFIG_FILE).exists():
            return Path(CONFIG_FILE)
        if Path(LEGACY_CONFIG).exists():
            return Path(LEGACY_CONFIG)
        return Path(CONFIG_FILE)

    # ── load / save ────────────────────────────────────────────────────

    def load(self):
        if not self._path.exists():
            self._data = dict(DEFAULTS)
            return

        try:
            if self._path.suffix in (".yaml", ".yml"):
                import yaml
                with open(self._path, encoding="utf-8") as f:
                    file_data = yaml.safe_load(f) or {}
            else:
                import json
                with open(self._path, encoding="utf-8") as f:
                    file_data = json.load(f)
                file_data = self._migrate_flat(file_data)

            self._data = _deep_merge(DEFAULTS, file_data)
            log.info("Config loaded from %s", self._path)
        except Exception as e:
            log.warning("Failed to load config: %s — using defaults", e)
            self._data = dict(DEFAULTS)

    def save(self, path: Optional[str] = None):
        target = Path(path) if path else self._path
        if target.suffix not in (".yaml", ".yml"):
            target = target.with_suffix(".yaml")
        try:
            import yaml
            with open(target, "w", encoding="utf-8") as f:
                yaml.dump(self._data, f, default_flow_style=False, sort_keys=False)
            log.info("Config saved to %s", target)
        except ImportError:
            import json
            json_path = target.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
            log.info("Config saved to %s (YAML unavailable, using JSON)", json_path)

    # ── access ─────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation access: config.get('adb.serial')."""
        parts = key.split(".")
        node = self._data
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                return default
        return node

    def set(self, key: str, value: Any):
        """Dot-notation set: config.set('adb.serial', '127.0.0.1:5565')."""
        parts = key.split(".")
        node = self._data
        for p in parts[:-1]:
            if p not in node or not isinstance(node[p], dict):
                node[p] = {}
            node = node[p]
        node[parts[-1]] = value

    def section(self, key: str) -> dict:
        """Return an entire config section."""
        val = self.get(key, {})
        return val if isinstance(val, dict) else {}

    @property
    def data(self) -> dict:
        return self._data

    # ── migration from legacy flat config.json ─────────────────────────

    @staticmethod
    def _migrate_flat(flat: dict) -> dict:
        """Convert legacy flat config.json to nested structure."""
        nested = {}
        mapping = {
            "adb_serial": "adb.serial",
            "auto_match_tap": "input.auto_match_tap",
            "accept_tap": "input.accept_tap",
            "auto_match_check": "detection.auto_match_check",
            "auto_match_color": "detection.auto_match_color",
            "auto_match_tolerance": "detection.auto_match_tolerance",
            "accept_check": "detection.accept_check",
            "accept_color": "detection.accept_color",
            "accept_tolerance": "detection.accept_tolerance",
            "pq_duration": "timings.pq_duration",
            "matchmaking_timeout": "timings.matchmaking_timeout",
            "accept_poll_interval": "timings.accept_poll_interval",
            "pre_queue_delay": "timings.pre_queue_delay",
            "post_reward_delay": "timings.post_reward_delay",
            "tap_spread": "input.tap_spread",
            "random_tap_interval": "timings.random_tap_interval",
            "random_tap_radius": "timings.random_tap_radius",
            "accept_reaction_delay": "timings.accept_reaction_delay",
            "calibrated": "calibrated",
        }

        for old_key, new_path in mapping.items():
            if old_key in flat:
                parts = new_path.split(".")
                node = nested
                for p in parts[:-1]:
                    node = node.setdefault(p, {})
                node[parts[-1]] = flat[old_key]

        # pass through any nested keys that already match the new format
        for k, v in flat.items():
            if k not in mapping and isinstance(v, dict):
                nested[k] = v

        return nested

    # ── utility ────────────────────────────────────────────────────────

    def create_example(self, path: str = "config/settings.yaml.example"):
        """Write a commented example config file."""
        example = """# MSM PQ Farmer — Configuration
# Copy this file to settings.yaml and edit as needed.

adb:
  serial: "127.0.0.1:5555"   # BlueStacks ADB address
  path: null                   # Path to adb.exe (null = auto-detect)

capture:
  method: auto                 # auto | win32 | adb
  cache_ttl: 0.1              # Screenshot cache TTL in seconds

quest:
  type: sleepywood             # sleepywood | ludibrium | orbis | zakum
  max_runs: 0                  # 0 = unlimited

detection:
  method: auto                 # auto | template | pixel
  confidence: 0.85             # Template matching confidence threshold (0.0-1.0)
  # Legacy pixel detection (used when no templates available)
  auto_match_check: [0.88, 0.86]
  auto_match_color: [187, 221, 34]
  auto_match_tolerance: 45
  accept_check: [0.46, 0.70]
  accept_color: [32, 187, 205]
  accept_tolerance: 40

input:
  auto_match_tap: [1700, 950]  # Auto Match button coordinates
  accept_tap: [960, 800]       # Accept button coordinates
  tap_spread: 10               # Random pixel offset on every tap

timings:
  pq_duration: 350             # Max seconds inside a PQ
  matchmaking_timeout: 180     # Max seconds in queue
  accept_poll_interval: 0.8    # Seconds between accept checks
  pre_queue_delay: [0, 20]     # Random delay before queueing [min, max]
  post_reward_delay: [6, 12]   # Delay after PQ reward [min, max]
  accept_reaction_delay: [0.5, 3.0]  # Delay before accepting [min, max]
  random_tap_interval: [30, 60]      # Idle tap interval [min, max]
  random_tap_radius: 200       # Idle tap radius from center

recovery:
  enabled: true
  soft_timeout: 120            # Seconds before soft recovery
  hard_timeout: 300            # Seconds before hard recovery
  max_queue_timeouts: 3        # Consecutive timeouts before restart
  app_package: "com.nexon.msm.global"

logging:
  console_level: INFO
  file_level: DEBUG
  max_log_files: 5

gui:
  theme: dark
  window_width: 1100
  window_height: 720
"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(example)
