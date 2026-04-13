"""Page frames for the GUI — Dashboard, Settings, and Log."""

import tkinter as tk
from gui.theme import COLORS, FONTS
from gui.widgets import Card, StatCard, StatusBadge, LogView


class DashboardPage(tk.Frame):
    """Main dashboard with stats, status, and recent log."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])

        # Header
        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="Dashboard", font=FONTS["title"],
                 fg=COLORS["text_bright"], bg=COLORS["bg"]).pack(side="left")

        # Stats row
        stats_frame = tk.Frame(self, bg=COLORS["bg"])
        stats_frame.pack(fill="x", padx=24, pady=(0, 16))
        stats_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")

        self.stat_runs = StatCard(stats_frame, "PQ Runs", "0", COLORS["accent"])
        self.stat_runs.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.stat_time = StatCard(stats_frame, "Körtid", "0:00", COLORS["green"])
        self.stat_time.grid(row=0, column=1, sticky="nsew", padx=4)

        self.stat_avg = StatCard(stats_frame, "Snitt / PQ", "--", COLORS["purple"])
        self.stat_avg.grid(row=0, column=2, sticky="nsew", padx=4)

        self.stat_rate = StatCard(stats_frame, "Lyckade", "0%", COLORS["yellow"])
        self.stat_rate.grid(row=0, column=3, sticky="nsew", padx=(8, 0))

        # Status card
        status_card = Card(self, "STATUS")
        status_card.pack(fill="x", padx=24, pady=(0, 16))

        status_inner = tk.Frame(status_card, bg=COLORS["card"], padx=16, pady=12)
        status_inner.pack(fill="x")

        row1 = tk.Frame(status_inner, bg=COLORS["card"])
        row1.pack(fill="x")
        tk.Label(row1, text="Bot:", font=FONTS["body"],
                 fg=COLORS["text_dim"], bg=COLORS["card"]).pack(side="left")
        self.bot_badge = StatusBadge(row1, "idle")
        self.bot_badge.pack(side="left", padx=(8, 24))

        tk.Label(row1, text="Spel:", font=FONTS["body"],
                 fg=COLORS["text_dim"], bg=COLORS["card"]).pack(side="left")
        self.game_badge = StatusBadge(row1, "unknown")
        self.game_badge.pack(side="left", padx=(8, 24))

        tk.Label(row1, text="Quest:", font=FONTS["body"],
                 fg=COLORS["text_dim"], bg=COLORS["card"]).pack(side="left")
        self.quest_label = tk.Label(row1, text="Sleepywood", font=FONTS["body"],
                                    fg=COLORS["accent"], bg=COLORS["card"])
        self.quest_label.pack(side="left", padx=(8, 0))

        # Mini log
        log_card = Card(self, "SENASTE AKTIVITET")
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
    """Settings panel with grouped options — beginner-friendly labels."""

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

        # Bind mousewheel
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Header
        tk.Label(self._inner, text="Inställningar", font=FONTS["title"],
                 fg=COLORS["text_bright"], bg=COLORS["bg"]).pack(anchor="w", padx=24, pady=(20, 16))

        # Connection section
        self._section("Anslutning", [
            ("adb.serial", "BlueStacks-adress", "127.0.0.1:5555",
             "Ändra bara om du har flera BlueStacks-instanser"),
        ])

        # Quest section
        self._quest_section()

        # Timing section
        self._section("Väntetider", [
            ("timings.pq_duration", "Max tid i PQ (sekunder)", "350",
             "Hur länge boten väntar inne i en Party Quest"),
            ("timings.matchmaking_timeout", "Kö-timeout (sekunder)", "180",
             "Hur länge boten väntar på en match"),
        ])

        # Anti-detection section
        self._section("Mänskligt beteende", [
            ("input.tap_spread", "Slumpmässig offset (pixlar)", "10",
             "Varje tryck landar lite olika — ser mer naturligt ut"),
            ("timings.accept_reaction_delay", "Reaktionstid (sek)", "0.5, 3.0",
             "Slumpmässig fördröjning innan Accept trycks"),
        ])

        # Recovery section
        self._section("Felhantering", [
            ("recovery.soft_timeout", "Mjuk återhämtning (sek)", "120",
             "Boten försöker lösa problemet själv efter denna tid"),
            ("recovery.hard_timeout", "Hård återhämtning (sek)", "300",
             "Boten startar om appen efter denna tid"),
        ])

        # Buttons
        btn_frame = tk.Frame(self._inner, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=24, pady=(16, 24))

        save_btn = tk.Button(btn_frame, text="Spara", font=FONTS["button"],
                             bg=COLORS["green_dim"], fg=COLORS["text_bright"],
                             activebackground=COLORS["green"], relief="flat",
                             padx=24, pady=8, cursor="hand2",
                             command=self._save)
        save_btn.pack(side="right", padx=(8, 0))

        reset_btn = tk.Button(btn_frame, text="Återställ", font=FONTS["button"],
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

            lbl = tk.Label(row, text=label, font=FONTS["body"],
                           fg=COLORS["text"], bg=COLORS["card"], anchor="w")
            lbl.pack(fill="x")

            hint_lbl = tk.Label(row, text=hint, font=FONTS["small"],
                                fg=COLORS["text_dim"], bg=COLORS["card"], anchor="w")
            hint_lbl.pack(fill="x")

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
        card = Card(self._inner, "Quest-typ")
        card.pack(fill="x", padx=24, pady=(0, 12))
        inner = tk.Frame(card, bg=COLORS["card"], padx=16, pady=12)
        inner.pack(fill="x")

        tk.Label(inner, text="Välj vilken Party Quest du vill farma",
                 font=FONTS["small"], fg=COLORS["text_dim"], bg=COLORS["card"]).pack(anchor="w")

        btn_frame = tk.Frame(inner, bg=COLORS["card"], pady=8)
        btn_frame.pack(fill="x")

        self._quest_var = tk.StringVar(value=self.config.get("quest.type", "sleepywood"))
        quests = [
            ("Sleepywood", "sleepywood"),
            ("Ludibrium", "ludibrium"),
            ("Orbis", "orbis"),
            ("Zakum", "zakum"),
        ]
        for text, val in quests:
            rb = tk.Radiobutton(btn_frame, text=text, variable=self._quest_var,
                                value=val, font=FONTS["body"], fg=COLORS["text"],
                                bg=COLORS["card"], selectcolor=COLORS["accent"],
                                activebackground=COLORS["card"],
                                activeforeground=COLORS["text_bright"],
                                indicatoron=0, padx=16, pady=8, relief="flat",
                                cursor="hand2", borderwidth=0,
                                highlightbackground=COLORS["border"],
                                highlightthickness=1)
            rb.pack(side="left", padx=(0, 8))

        # Max runs
        row = tk.Frame(inner, bg=COLORS["card"], pady=4)
        row.pack(fill="x")
        tk.Label(row, text="Max antal PQ (0 = oändligt)", font=FONTS["body"],
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
                    parts = [float(v.strip()) for v in val.split(",")]
                    self.config.set(key, parts)
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
    """Full-screen log viewer with filters."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])

        # Header with controls
        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="Logg", font=FONTS["title"],
                 fg=COLORS["text_bright"], bg=COLORS["bg"]).pack(side="left")

        clear_btn = tk.Button(header, text="Rensa", font=FONTS["small"],
                              bg=COLORS["btn"], fg=COLORS["text"],
                              activebackground=COLORS["btn_hover"], relief="flat",
                              padx=12, pady=4, cursor="hand2",
                              command=self._clear)
        clear_btn.pack(side="right")

        # Log view
        self.log_view = LogView(self, max_lines=1000)
        self.log_view.pack(fill="both", expand=True, padx=24, pady=(0, 20))

    def _clear(self):
        self.log_view.clear()
