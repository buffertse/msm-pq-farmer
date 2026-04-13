"""
MSM PQ Farmer — MapleStory Idle RPG Party Quest auto-farmer for BlueStacks.
Entry point with GUI (default) and CLI modes.
"""

import sys
import argparse
import logging

VERSION = "2.0.0"


def run_gui():
    """Launch the graphical interface."""
    from gui.app import BotApp
    app = BotApp()
    app.run()


def run_cli(args):
    """Run in headless CLI mode (legacy)."""
    from core.logger import setup_logger
    from core.adb_controller import ADBController
    from core.screen_capture import ScreenCapture
    from core.template_matcher import TemplateMatcher
    from core.input_handler import InputHandler
    from config import ConfigManager
    from games.pq_farmer import PQFarmer, QuestType

    logger = setup_logger(
        console_level=logging.DEBUG if args.debug else logging.INFO,
    )
    log = logging.getLogger("msm-pq-farmer")

    config = ConfigManager(args.config)
    if args.serial:
        config.set("adb.serial", args.serial)
    if args.max_runs:
        config.set("quest.max_runs", args.max_runs)
    if args.quest:
        config.set("quest.type", args.quest)

    adb = ADBController(
        adb_path=args.adb,
        serial=config.get("adb.serial", "127.0.0.1:5555"),
    )

    if not adb.available:
        log.info("ADB not found — downloading...")
        path = ADBController.download_adb()
        if not path:
            log.error("Could not install ADB. Download manually from:")
            log.error("https://developer.android.com/tools/releases/platform-tools")
            sys.exit(1)
        adb = ADBController(adb_path=path, serial=config.get("adb.serial"))

    if not adb.auto_connect():
        log.error("Could not connect to BlueStacks. Make sure it is running")
        log.error("and ADB is enabled: Settings > Advanced > Android Debug Bridge")
        sys.exit(1)

    capture = ScreenCapture(adb)
    capture.find_window()
    matcher = TemplateMatcher()
    inp = InputHandler(adb, spread=config.get("input.tap_spread", 10))

    try:
        quest = QuestType(config.get("quest.type", "sleepywood"))
    except ValueError:
        quest = QuestType.SLEEPYWOOD

    bot = PQFarmer(
        adb=adb, capture=capture, matcher=matcher, inp=inp,
        config=config.data, quest_type=quest,
    )
    bot.dry_run = args.dry_run
    bot.start()


def main():
    ap = argparse.ArgumentParser(
        prog="msm-pq-farmer",
        description="MapleStory Idle RPG Party Quest auto-farmer for BlueStacks",
    )
    ap.add_argument("--cli", action="store_true",
                    help="run in CLI mode (no GUI)")
    ap.add_argument("--gui", action="store_true",
                    help="run in GUI mode (default)")
    ap.add_argument("-n", "--max-runs", type=int, default=0,
                    help="stop after N runs (0 = unlimited)")
    ap.add_argument("--dry-run", action="store_true",
                    help="detect states but don't send taps")
    ap.add_argument("--quest", choices=["sleepywood", "ludibrium", "orbis", "zakum"],
                    help="quest type")
    ap.add_argument("--serial", help="ADB device address")
    ap.add_argument("--adb", help="path to adb.exe")
    ap.add_argument("--config", default=None, help="config file path")
    ap.add_argument("--debug", action="store_true", help="verbose logging")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args()

    if args.cli:
        run_cli(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()
