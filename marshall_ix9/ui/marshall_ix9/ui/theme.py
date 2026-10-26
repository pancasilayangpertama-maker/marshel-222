"""Palette, fonts and DPI scaling. Edit the colours here to re-skin the whole app.

The look comes from the name: a Marshall-style amp head. Warm tolex black, brass trim, level meters,
one big knob that goes up to eleven.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

BG = "#0d0c0b"        # tolex black
SIDEBAR = "#100f0d"
PANEL = "#171512"
RAISED = "#201d19"
LINE = "#352f27"
BRASS = "#d6a94a"
BRASS_HI = "#f0cb73"
BRASS_LO = "#7b6230"
CREAM = "#efe6d2"
MUTED = "#9b9080"
INK = "#14110c"       # text that sits on brass
RED = "#ff4433"
GREEN = "#7fd49a"
ORANGE = "#f0954a"
LED_OFF = "#2a251f"

SCALE = 1.0


def px(value: float) -> int:
    """Scale a design pixel to the real screen (high-DPI laptops)."""
    return max(1, int(round(value * SCALE)))


def init(root: tk.Misc) -> None:
    """Call once, right after the Tk root exists."""
    global SCALE
    try:
        SCALE = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
    except Exception:
        SCALE = 1.0
    families = set(tkfont.families(root))

    def pick(*names: str) -> str:
        for name in names:
            if name in families:
                return name
        return tkfont.nametofont("TkDefaultFont").actual("family")

    head = pick("Bahnschrift", "Segoe UI Semibold", "Segoe UI")
    body = pick("Segoe UI", "Helvetica", "Arial")
    mono = pick("Cascadia Mono", "Consolas", "Courier New")

    specs = {
        "ix9.hero": (head, 26, "bold"),
        "ix9.title": (head, 18, "bold"),
        "ix9.h2": (head, 12, "bold"),
        "ix9.big": (head, 22, "bold"),
        "ix9.nav": (head, 11, "bold"),
        "ix9.btn": (head, 10, "bold"),
        "ix9.body": (body, 10, "normal"),
        "ix9.bodyb": (body, 10, "bold"),
        "ix9.small": (body, 9, "normal"),
        "ix9.mono": (mono, 9, "normal"),
    }
    for name, (family, size, weight) in specs.items():
        try:
            tkfont.Font(root=root, name=name, family=family, size=size, weight=weight)
        except tk.TclError:  # already defined (second call): just update it
            tkfont.nametofont(name, root=root).configure(family=family, size=size, weight=weight)
