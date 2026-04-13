"""
Main GUI application — advanced dark-themed bot launcher.
Beginner-friendly: auto-detects everything, guides the user step-by-step.
"""

import tkinter as tk
import threading
import logging

from gui.theme import COLORS, FONTS
from gui.widgets import SidebarButton, StatusBadge
from gui.pages import DashboardPage, SettingsPage, LogPage
from core.logger import LogCallback, setup_logger
from core.adb_controller import ADBController
from core.screen_capture import ScreenCapture
from core.template_matcher import TemplateMatcher
from core.input_handler import InputHandler
from config import ConfigManager
from games.pq_farmer import PQFarmer, QuestType

log = logging.getLogger("msm-pq-farmer")


class BotApp:
    """The main application window."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MSM PQ Farmer")
        self.root.configure(bg=COLORS["bg"])
        self.root.minsize(900, 600)

        # Config
        self.config = ConfigManager()
        w = self.config.get("gui.window_width", 1100)
        h = self.config.get("gui.window_height", 720)
        self.root.geometry(f"{w}x{h}")

        # Try to set icon
        try:
            self.root.iconbitmap("favicon.ico")
        except Exception:
            pass

        # Log callback for GUI
        self.log_callback = LogCallback()
        self.logger = setup_logger(log_callback=self.log_callback)

        # Core components (initialised later on connect)
        self.adb = ADBController(
            adb_path=self.config.get("adb.path"),
            serial=self.config.get("adb.serial", "127.0.0.1:5555"),
        )
        self.capture = ScreenCapture(self.adb)
        self.matcher = TemplateMatcher()
        self.input_handler = InputHandler(self.adb, spread=self.config.get("input.tap_spread", 10))
        self.bot: PQFarmer = None
        self._bot_thread: threading.Thread = None

        self._build_ui()
        self._bind_log_callback()
        self._auto_setup()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self):
        # Main layout: sidebar + content
        self._main = tk.Frame(self.root, bg=COLORS["bg"])
        self._main.pack(fill="both", expand=True)

        # Sidebar
        sidebar = tk.Frame(self._main, bg=COLORS["sidebar"], width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Logo area
        logo_frame = tk.Frame(sidebar, bg=COLORS["sidebar"], pady=20, padx=16)
        logo_frame.pack(fill="x")
        tk.Label(logo_frame, text="MSM PQ", font=("Segoe UI", 18, "bold"),
                 fg=COLORS["accent"], bg=COLORS["sidebar"]).pack(anchor="w")
        tk.Label(logo_frame, text="FARMER", font=("Segoe UI", 18, "bold"),
                 fg=COLORS["text_bright"], bg=COLORS["sidebar"]).pack(anchor="w")
        tk.Label(logo_frame, text="v2.0", font=FONTS["small"],
                 fg=COLORS["text_dim"], bg=COLORS["sidebar"]).pack(anchor="w", pady=(2, 0))

        sep = tk.Frame(sidebar, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=16, pady=(0, 8))

        # Navigation buttons
        self._nav_buttons = []
        pages = [
            ("\u25a3", "Dashboard", True),
            ("\u2699", "Inställningar", False),
            ("\u2261", "Logg", False),
        ]
        for icon, text, active in pages:
            btn = SidebarButton(sidebar, text, icon,
                                command=lambda t=text: self._switch_page(t),
                                active=active)
            btn.pack(fill="x")
            self._nav_buttons.append((text, btn))

        # Connection status at bottom of sidebar
        spacer = tk.Frame(sidebar, bg=COLORS["sidebar"])
        spacer.pack(fill="both", expand=True)

        conn_frame = tk.Frame(sidebar, bg=COLORS["sidebar"], padx=16, pady=12)
        conn_frame.pack(fill="x", side="bottom")
        sep2 = tk.Frame(sidebar, bg=COLORS["border"], height=1)
        sep2.pack(fill="x", padx=16, side="bottom")

        self.conn_badge = StatusBadge(conn_frame, "disconnected")
        self.conn_badge.config(bg=COLORS["sidebar"])
        for child in self.conn_badge.winfo_children():
            child.config(bg=COLORS["sidebar"])
        self.conn_badge.pack(anchor="w")
        self._conn_label = tk.Label(conn_frame, text="", font=FONTS["small"],
                                    fg=COLORS["text_dim"], bg=COLORS["sidebar"])
        self._conn_label.pack(anchor="w")

        # Content area
        self._content = tk.Frame(self._main, bg=COLORS["bg"])
        self._content.pack(side="left", fill="both", expand=True)

        # Pages
        self._pages = {}
        self._pages["Dashboard"] = DashboardPage(self._content)
        self._pages["Inställningar"] = SettingsPage(self._content, self.config, self._on_settings_saved)
        self._pages["Logg"] = LogPage(self._content)
        self._current_page = "Dashboard"
        self._pages["Dashboard"].pack(fill="both", expand=True)

        # Bottom control bar
        self._build_control_bar()

    def _build_control_bar(self):
        bar = tk.Frame(self.root, bg=COLORS["bg2"], height=60)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        sep = tk.Frame(self.root, bg=COLORS["border"], height=1)
        sep.pack(fill="x", side="bottom")

        inner = tk.Frame(bar, bg=COLORS["bg2"], padx=20)
        inner.pack(fill="both", expand=True)

        # Left: status text
        self._status_text = tk.Label(inner, text="Klicka Start för att börja",
                                     font=FONTS["body"], fg=COLORS["text_dim"],
                                     bg=COLORS["bg2"], anchor="w")
        self._status_text.pack(side="left", fill="x", expand=True)

        # Right: control buttons
        self._stop_btn = tk.Button(inner, text="\u25a0  Stopp", font=FONTS["button"],
                                   bg=COLORS["btn"], fg=COLORS["text"],
                                   activebackground=COLORS["red"],
                                   relief="flat", padx=16, pady=6, cursor="hand2",
                                   command=self._on_stop, state="disabled")
        self._stop_btn.pack(side="right", padx=(8, 0))

        self._pause_btn = tk.Button(inner, text="\u23f8  Paus", font=FONTS["button"],
                                    bg=COLORS["btn"], fg=COLORS["text"],
                                    activebackground=COLORS["yellow"],
                                    relief="flat", padx=16, pady=6, cursor="hand2",
                                    command=self._on_pause, state="disabled")
        self._pause_btn.pack(side="right", padx=(8, 0))

        self._start_btn = tk.Button(inner, text="\u25b6  Start", font=FONTS["button"],
                                    bg=COLORS["green_dim"], fg=COLORS["text_bright"],
                                    activebackground=COLORS["green"],
                                    relief="flat", padx=24, pady=6, cursor="hand2",
                                    command=self._on_start)
        self._start_btn.pack(side="right")

    # ── navigation ─────────────────────────────────────────────────────

    def _switch_page(self, name):
        if name == self._current_page:
            return
        self._pages[self._current_page].pack_forget()
        self._pages[name].pack(fill="both", expand=True)
        self._current_page = name

        for btn_name, btn in self._nav_buttons:
            btn.set_active(btn_name == name)

    # ── log callback ───────────────────────────────────────────────────

    def _bind_log_callback(self):
        def on_log(level, message, timestamp):
            self.root.after(0, self._handle_log, level, message, timestamp)
        self.log_callback.add(on_log)

    def _handle_log(self, level, message, timestamp):
        dashboard = self._pages["Dashboard"]
        log_page = self._pages["Logg"]
        dashboard.log_view.add(level, message, timestamp)
        log_page.log_view.add(level, message, timestamp)

    # ── auto-setup (beginner-friendly) ─────────────────────────────────

    def _auto_setup(self):
        """Run auto-detection in a thread so the GUI doesn't freeze."""
        self._status_text.config(text="Startar automatisk konfiguration...")
        threading.Thread(target=self._auto_setup_worker, daemon=True).start()

    def _auto_setup_worker(self):
        # Step 1: Find ADB
        if not self.adb.available:
            self.root.after(0, self._status_text.config,
                            {"text": "Laddar ner ADB... (första gången)"})
            path = ADBController.download_adb()
            if path:
                self.adb = ADBController(adb_path=path,
                                         serial=self.config.get("adb.serial", "127.0.0.1:5555"))
                self.capture = ScreenCapture(self.adb)
                self.input_handler = InputHandler(self.adb)
            else:
                self.root.after(0, self._status_text.config,
                                {"text": "ADB hittades inte — installera manuellt"})
                return

        # Step 2: Connect to BlueStacks
        log.info("Söker efter BlueStacks...")
        if self.adb.auto_connect():
            self.root.after(0, self._on_connected)
        else:
            self.root.after(0, self._status_text.config,
                            {"text": "Starta BlueStacks och öppna spelet — klicka sedan Start"})
            self.root.after(0, self.conn_badge.set, "disconnected")

    def _on_connected(self):
        self.conn_badge.set("connected")
        self._conn_label.config(text=self.adb.serial)
        self._status_text.config(text="Ansluten! Klicka Start för att börja farma")
        self.capture.find_window()

    # ── bot control ────────────────────────────────────────────────────

    def _on_start(self):
        if self.bot and self.bot.state.value == "running":
            return

        # Try connecting if not connected
        if not self.adb.connected:
            self._status_text.config(text="Ansluter...")
            if not self.adb.auto_connect():
                self._status_text.config(text="Kunde inte ansluta — starta BlueStacks först")
                return
            self._on_connected()

        quest_str = self.config.get("quest.type", "sleepywood")
        try:
            quest = QuestType(quest_str)
        except ValueError:
            quest = QuestType.SLEEPYWOOD

        self.bot = PQFarmer(
            adb=self.adb,
            capture=self.capture,
            matcher=self.matcher,
            inp=self.input_handler,
            config=self.config.data,
            quest_type=quest,
        )
        self.bot.on_state_change = lambda bs, gs: self.root.after(0, self._on_state_change, bs, gs)
        self.bot.on_stats_update = lambda s: self.root.after(0, self._on_stats_update, s)

        self._start_btn.config(state="disabled")
        self._pause_btn.config(state="normal")
        self._stop_btn.config(state="normal")
        self._status_text.config(text="Boten kör...")

        self._bot_thread = self.bot.start_threaded()

    def _on_pause(self):
        if not self.bot:
            return
        if self.bot.state.value == "running":
            self.bot.pause()
            self._pause_btn.config(text="\u25b6  Fortsätt")
            self._status_text.config(text="Pausad")
        elif self.bot.state.value == "paused":
            self.bot.resume()
            self._pause_btn.config(text="\u23f8  Paus")
            self._status_text.config(text="Boten kör...")

    def _on_stop(self):
        if self.bot:
            self.bot.stop()
        self._start_btn.config(state="normal")
        self._pause_btn.config(state="disabled", text="\u23f8  Paus")
        self._stop_btn.config(state="disabled")
        self._status_text.config(text="Stoppad")

    def _on_state_change(self, bot_state, game_state):
        dashboard = self._pages["Dashboard"]
        dashboard.bot_badge.set(bot_state)
        dashboard.game_badge.set(game_state)

    def _on_stats_update(self, stats):
        dashboard = self._pages["Dashboard"]
        dashboard.update_stats(stats)

    def _on_settings_saved(self):
        log.info("Inställningar sparade")
        self._status_text.config(text="Inställningar sparade!")

    # ── run ────────────────────────────────────────────────────────────

    def run(self):
        # Center window
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

        self.root.protocol("WM_DELETE_CLOSE", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.bot:
            self.bot.stop()
        self.root.destroy()
