"""Reusable custom widgets for the GUI."""

import tkinter as tk
from gui.theme import COLORS, FONTS


class Card(tk.Frame):
    """A styled card container with optional title."""

    def __init__(self, parent, title="", **kw):
        super().__init__(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                         highlightthickness=1, **kw)
        if title:
            lbl = tk.Label(self, text=title, font=FONTS["heading"],
                           fg=COLORS["text_dim"], bg=COLORS["card"], anchor="w")
            lbl.pack(fill="x", padx=16, pady=(12, 4))


class StatCard(tk.Frame):
    """A card showing a single stat with label and value."""

    def __init__(self, parent, label, value="0", color=None):
        super().__init__(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                         highlightthickness=1, padx=16, pady=12)
        self._color = color or COLORS["accent"]
        dot = tk.Label(self, text="\u25cf", font=("Segoe UI", 8), fg=self._color, bg=COLORS["card"])
        dot.pack(side="left", padx=(0, 6))
        right = tk.Frame(self, bg=COLORS["card"])
        right.pack(side="left", fill="both", expand=True)
        self._lbl = tk.Label(right, text=label.upper(), font=FONTS["small"],
                             fg=COLORS["text_dim"], bg=COLORS["card"], anchor="w")
        self._lbl.pack(fill="x")
        self._val = tk.Label(right, text=value, font=FONTS["big_number"],
                             fg=COLORS["text_bright"], bg=COLORS["card"], anchor="w")
        self._val.pack(fill="x")

    def set_value(self, v):
        self._val.config(text=str(v))


class StatusBadge(tk.Frame):
    """A colored status badge with dot indicator."""

    STATUS_COLORS = {
        "idle": COLORS["text_dim"],
        "running": COLORS["green"],
        "paused": COLORS["yellow"],
        "stopped": COLORS["red"],
        "menu": COLORS["accent"],
        "accept": COLORS["green"],
        "queued": COLORS["yellow"],
        "in_pq": COLORS["green"],
        "loading": COLORS["orange"],
        "unknown": COLORS["text_dim"],
        "connected": COLORS["green"],
        "disconnected": COLORS["red"],
    }

    FRIENDLY_NAMES = {
        "idle": "Redo",
        "running": "Kör",
        "paused": "Pausad",
        "stopped": "Stoppad",
        "menu": "Huvudmeny",
        "accept": "Acceptera match",
        "queued": "I kö",
        "in_pq": "I Party Quest",
        "loading": "Laddar...",
        "unknown": "Söker...",
        "connected": "Ansluten",
        "disconnected": "Ej ansluten",
    }

    def __init__(self, parent, status="idle"):
        super().__init__(parent, bg=COLORS["card"])
        self._dot = tk.Label(self, text="\u25cf", font=("Segoe UI", 10),
                             fg=COLORS["text_dim"], bg=COLORS["card"])
        self._dot.pack(side="left", padx=(0, 6))
        self._text = tk.Label(self, text="", font=FONTS["body"],
                              fg=COLORS["text"], bg=COLORS["card"])
        self._text.pack(side="left")
        self.set(status)

    def set(self, status: str):
        color = self.STATUS_COLORS.get(status, COLORS["text_dim"])
        name = self.FRIENDLY_NAMES.get(status, status)
        self._dot.config(fg=color)
        self._text.config(text=name)


class LogView(tk.Frame):
    """Scrollable log viewer with colored entries."""

    LEVEL_COLORS = {
        "DEBUG": COLORS["text_dim"],
        "INFO": COLORS["text"],
        "WARNING": COLORS["yellow"],
        "ERROR": COLORS["red"],
        "CRITICAL": COLORS["red"],
    }

    def __init__(self, parent, max_lines=500):
        super().__init__(parent, bg=COLORS["bg2"])
        self.max_lines = max_lines
        self._text = tk.Text(self, bg=COLORS["bg"], fg=COLORS["text"],
                             font=FONTS["mono"], wrap="word", relief="flat",
                             borderwidth=0, highlightthickness=0,
                             insertbackground=COLORS["text"], state="disabled",
                             padx=12, pady=8)
        sb = tk.Scrollbar(self, command=self._text.yview,
                          bg=COLORS["bg3"], troughcolor=COLORS["bg"],
                          highlightthickness=0, borderwidth=0)
        self._text.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._text.pack(fill="both", expand=True)

        for level, color in self.LEVEL_COLORS.items():
            self._text.tag_config(level, foreground=color)
        self._text.tag_config("TIMESTAMP", foreground=COLORS["text_dim"])
        self._line_count = 0

    def add(self, level: str, message: str, timestamp: str):
        self._text.config(state="normal")
        if self._line_count > 0:
            self._text.insert("end", "\n")
        self._text.insert("end", f"{timestamp} ", "TIMESTAMP")
        self._text.insert("end", message, level)
        self._line_count += 1

        if self._line_count > self.max_lines:
            self._text.delete("1.0", "2.0")
            self._line_count -= 1

        self._text.config(state="disabled")
        self._text.see("end")

    def clear(self):
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")
        self._line_count = 0


class SidebarButton(tk.Frame):
    """A sidebar navigation button."""

    def __init__(self, parent, text, icon="", command=None, active=False):
        super().__init__(parent, bg=COLORS["sidebar"], cursor="hand2")
        self._command = command
        self._active = False
        self._icon_text = icon
        self._btn_text = text

        inner = tk.Frame(self, bg=COLORS["sidebar"], padx=16, pady=10)
        inner.pack(fill="x")

        if icon:
            self._icon = tk.Label(inner, text=icon, font=("Segoe UI", 13),
                                  fg=COLORS["text_dim"], bg=COLORS["sidebar"])
            self._icon.pack(side="left", padx=(0, 10))
        else:
            self._icon = None

        self._label = tk.Label(inner, text=text, font=FONTS["sidebar"],
                               fg=COLORS["text_dim"], bg=COLORS["sidebar"],
                               anchor="w")
        self._label.pack(side="left", fill="x")

        self._indicator = tk.Frame(self, bg=COLORS["sidebar"], width=3, height=0)
        self._indicator.place(x=0, y=0, relheight=1, width=3)

        for w in [self, inner, self._label]:
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
        if self._icon:
            self._icon.bind("<Button-1>", self._on_click)
            self._icon.bind("<Enter>", self._on_enter)
            self._icon.bind("<Leave>", self._on_leave)

        if active:
            self.set_active(True)

    def _on_click(self, _=None):
        if self._command:
            self._command()

    def _on_enter(self, _=None):
        if not self._active:
            self.config(bg=COLORS["bg"])
            for child in self.winfo_children():
                self._set_bg_recursive(child, COLORS["bg"])

    def _on_leave(self, _=None):
        if not self._active:
            bg = COLORS["sidebar"]
            self.config(bg=bg)
            for child in self.winfo_children():
                self._set_bg_recursive(child, bg)

    def _set_bg_recursive(self, widget, bg):
        try:
            widget.config(bg=bg)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_bg_recursive(child, bg)

    def set_active(self, active: bool):
        self._active = active
        if active:
            bg = COLORS["bg2"]
            self._label.config(font=FONTS["sidebar_active"], fg=COLORS["text_bright"])
            if self._icon:
                self._icon.config(fg=COLORS["accent"])
            self._indicator.config(bg=COLORS["accent"])
        else:
            bg = COLORS["sidebar"]
            self._label.config(font=FONTS["sidebar"], fg=COLORS["text_dim"])
            if self._icon:
                self._icon.config(fg=COLORS["text_dim"])
            self._indicator.config(bg=COLORS["sidebar"])
        self.config(bg=bg)
        for child in self.winfo_children():
            self._set_bg_recursive(child, bg)
