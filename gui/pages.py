"""Page frames for the GUI — Dashboard, Settings, and Log."""

import tkinter as tk
from gui.theme import COLORS, FONTS
from gui.widgets import Card, StatCard, StatusBadge, LogView


class DashboardPage(tk.Frame):
    """Main dashboard with stats, status, and recent log."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])

        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="Dashboard", font=FONTS["title"],
                 fg=COLORS["text_bright"], bg=COLORS["bg"]).pack(side="left")

        # Stats row
        stats_frame = tk.Frame(self, bg=COLORS["bg"])
        stats_frame.pack(fill="x", padx=24, pady=(0, 16))
        stats_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")

        self.stat_runs = StatCard(stats_frame, "PQ Runs", "0", COLORS["accent"])
        self.stat_runs.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.stat_time = StatCard(stats_frame, "Runtime", "0:00", COLORS["green"])
        self.stat_time.grid(row=0, column=1, sticky="nsew", padx=3)

        self.stat_avg = StatCard(stats_frame, "Avg / PQ", "--", COLORS["purple"])
        self.stat_avg.grid(row=0, column=2, sticky="nsew", padx=3)

        self.stat_rate = StatCard(stats_frame, "Success", "0%", COLORS["orange"])
        self.stat_rate.grid(row=0, column=3, sticky="nsew", padx=(6, 0))

        # Status card
        status_card = Card(self, "STATUS")
        status_card.pack(fill="x", padx=24, pady=(0, 16))

        status_inner = tk.Frame(status_card, bg=COLORS["card"], padx=16, pady=10)
        status_inner.pack(fill="x")

        row1 = tk.Frame(status_inner, bg=COLORS["card"])
        row1.pack(fill="x")
        tk.Label(row1, text="Bot:", font=FONTS["body"],
                 fg=COLORS["text_dim"], bg=COLORS["card"]).pack(side="left")
        self.bot_badge = StatusBadge(row1, "idle")
        self.bot_badge.pack(side="left", padx=(8, 24))

        tk.Label(row1, text="Game:", font=FONTS["body"],
                 fg=COLORS["text_dim"], bg=COLORS["card"]).pack(side="left")
        self.game_badge = StatusBadge(row1, "unknown")
        self.game_badge.pack(side="left", padx=(8, 24))

        tk.Label(row1, text="Quest:", font=FONTS["body"],
                 fg=COLORS["text_dim"], bg=COLORS["card"]).pack(side="left")
        self.quest_label = tk.Label(row1, text="Sleepywood", font=FONTS["body"],
                                    fg=COLORS["accent"], bg=COLORS["card"])
        self.quest_label.pack(side="left", padx=(8, 0))

        # Mini log
        log_card = Card(self, "RECENT ACTIVITY")
        log_card.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        self.log_view = LogView(log_card, max_lines=200)
        self.log_view.pack(fill="both", expand=True, padx=1, pady=(0, 1))

    def update_stats(self, stats: dict):
        self.stat_runs.set_value(str(stats.get("pq_runs", 0)))

        runtime = stats.get("runtime", 0)
        h, rem = divmod(int(runtime), 3600)
        m, s = divmod(rem, 60)
        self.stat_time.set_value(f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")

        avg = stats.get("avg_pq_time", 0)
        if avg > 0:
            am, asec = divmod(int(avg), 60)
            self.stat_avg.set_value(f"{am}:{asec:02d}")
        else:
            self.stat_avg.set_value("--")

        rate = stats.get("success_rate", 0)
        self.stat_rate.set_value(f"{rate:.0f}%")


class SettingsPage(tk.Frame):
    """Settings panel with grouped options."""

    def __init__(self, parent, config, on_save=None):
        super().__init__(parent, bg=COLORS["bg"])
        self.config = config
        self._on_save = on_save
        self._entries = {}

        canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self._inner = tk.Frame(canvas, bg=COLORS["bg"])

        self._inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Header
        tk.Label(self._inner, text="Settings", font=FONTS["title"],
                 fg=COLORS["text_bright"], bg=COLORS["bg"]).pack(anchor="w", padx=24, pady=(20, 16))

        # Connection
        self._section("Connection", [
            ("adb.serial", "BlueStacks address", "127.0.0.1:5555",
             "Only change if you have multiple BlueStacks instances"),
        ])

        # Quest
        self._quest_section()

        # Timings
        self._section("Timings", [
            ("timings.pq_duration", "Max PQ duration (seconds)", "350",
             "How long the bot waits inside a Party Quest"),
            ("timings.matchmaking_timeout", "Queue timeout (seconds)", "180",
             "How long the bot waits for a match"),
        ])

        # Anti-detection
        self._section("Human Behaviour", [
            ("input.tap_spread", "Random offset (pixels)", "10",
             "Each tap lands slightly differently to look natural"),
            ("timings.accept_reaction_delay", "Reaction delay (sec)", "0.5, 3.0",
             "Random delay before tapping Accept"),
        ])

        # Recovery
        self._section("Recovery", [
            ("recovery.soft_timeout", "Soft recovery (sec)", "120",
             "Bot tries to fix the problem itself after this time"),
            ("recovery.hard_timeout", "Hard recovery (sec)", "300",
             "Bot restarts the app after this time"),
        ])

        # Buttons
        btn_frame = tk.Frame(self._inner, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=24, pady=(16, 24))

        save_btn = tk.Button(btn_frame, text="Save", font=FONTS["button"],
                             bg=COLORS["green_dim"], fg=COLORS["text_bright"],
                             activebackground=COLORS["green"], relief="flat",
                             padx=24, pady=8, cursor="hand2",
                             command=self._save)
        save_btn.pack(side="right", padx=(8, 0))

        reset_btn = tk.Button(btn_frame, text="Reset Defaults", font=FONTS["button"],
                              bg=COLORS["btn"], fg=COLORS["text"],
                              activebackground=COLORS["btn_hover"], relief="flat",
                              padx=24, pady=8, cursor="hand2",
                              command=self._reset)
        reset_btn.pack(side="right")

    def _section(self, title, fields):
        card = Card(self._inner, title)
        card.pack(fill="x", padx=24, pady=(0, 12))
        inner = tk.Frame(card, bg=COLORS["card"], padx=16, pady=8)
        inner.pack(fill="x")

        for key, label, default, hint in fields:
            row = tk.Frame(inner, bg=COLORS["card"], pady=4)
            row.pack(fill="x")

            tk.Label(row, text=label, font=FONTS["body"],
                     fg=COLORS["text"], bg=COLORS["card"], anchor="w").pack(fill="x")
            tk.Label(row, text=hint, font=FONTS["small"],
                     fg=COLORS["text_dim"], bg=COLORS["card"], anchor="w").pack(fill="x")

            val = self.config.get(key)
            if isinstance(val, list):
                display = ", ".join(str(v) for v in val)
            elif val is not None:
                display = str(val)
            else:
                display = default

            entry = tk.Entry(row, font=FONTS["mono"], bg=COLORS["input_bg"],
                             fg=COLORS["text_bright"], insertbackground=COLORS["text"],
                             relief="flat", highlightbackground=COLORS["border"],
                             highlightthickness=1, highlightcolor=COLORS["accent"])
            entry.insert(0, display)
            entry.pack(fill="x", pady=(4, 8))
            self._entries[key] = entry

    def _quest_section(self):
        card = Card(self._inner, "Quest Type")
        card.pack(fill="x", padx=24, pady=(0, 12))
        inner = tk.Frame(card, bg=COLORS["card"], padx=16, pady=12)
        inner.pack(fill="x")

        tk.Label(inner, text="Select which Party Quest to farm",
                 font=FONTS["small"], fg=COLORS["text_dim"], bg=COLORS["card"]).pack(anchor="w")

        btn_frame = tk.Frame(inner, bg=COLORS["card"], pady=8)
        btn_frame.pack(fill="x")

        self._quest_var = tk.StringVar(value=self.config.get("quest.type", "sleepywood"))
        for text, val in [("Sleepywood", "sleepywood"), ("Ludibrium", "ludibrium"),
                          ("Orbis", "orbis"), ("Zakum", "zakum")]:
            rb = tk.Radiobutton(btn_frame, text=text, variable=self._quest_var,
                                value=val, font=FONTS["body"], fg=COLORS["text"],
                                bg=COLORS["card"], selectcolor=COLORS["accent"],
                                activebackground=COLORS["card"],
                                activeforeground=COLORS["text_bright"],
                                indicatoron=0, padx=16, pady=6, relief="flat",
                                cursor="hand2", borderwidth=0,
                                highlightbackground=COLORS["border"],
                                highlightthickness=1)
            rb.pack(side="left", padx=(0, 6))

        row = tk.Frame(inner, bg=COLORS["card"], pady=4)
        row.pack(fill="x")
        tk.Label(row, text="Max runs (0 = unlimited)", font=FONTS["body"],
                 fg=COLORS["text"], bg=COLORS["card"]).pack(anchor="w")
        self._max_runs = tk.Entry(row, font=FONTS["mono"], bg=COLORS["input_bg"],
                                  fg=COLORS["text_bright"], insertbackground=COLORS["text"],
                                  relief="flat", highlightbackground=COLORS["border"],
                                  highlightthickness=1, width=10)
        self._max_runs.insert(0, str(self.config.get("quest.max_runs", 0)))
        self._max_runs.pack(anchor="w", pady=(4, 0))

    def _save(self):
        for key, entry in self._entries.items():
            val = entry.get().strip()
            if "," in val:
                try:
                    self.config.set(key, [float(v.strip()) for v in val.split(",")])
                except ValueError:
                    self.config.set(key, val)
            else:
                try:
                    self.config.set(key, int(val))
                except ValueError:
                    try:
                        self.config.set(key, float(val))
                    except ValueError:
                        self.config.set(key, val)

        self.config.set("quest.type", self._quest_var.get())
        try:
            self.config.set("quest.max_runs", int(self._max_runs.get()))
        except ValueError:
            pass

        self.config.save()
        if self._on_save:
            self._on_save()

    def _reset(self):
        from config import DEFAULTS
        for key, entry in self._entries.items():
            parts = key.split(".")
            node = DEFAULTS
            for p in parts:
                if isinstance(node, dict) and p in node:
                    node = node[p]
                else:
                    node = ""
                    break
            entry.delete(0, "end")
            if isinstance(node, list):
                entry.insert(0, ", ".join(str(v) for v in node))
            else:
                entry.insert(0, str(node))


class LogPage(tk.Frame):
    """Full-screen log viewer."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])

        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="Log", font=FONTS["title"],
                 fg=COLORS["text_bright"], bg=COLORS["bg"]).pack(side="left")

        clear_btn = tk.Button(header, text="Clear", font=FONTS["small"],
                              bg=COLORS["btn"], fg=COLORS["text"],
                              activebackground=COLORS["btn_hover"], relief="flat",
                              padx=12, pady=4, cursor="hand2",
                              command=self._clear)
        clear_btn.pack(side="right")

        self.log_view = LogView(self, max_lines=1000)
        self.log_view.pack(fill="both", expand=True, padx=24, pady=(0, 20))

    def _clear(self):
        self.log_view.clear()
