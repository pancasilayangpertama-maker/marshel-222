"""Small custom widgets. Plain Tk only (no extra packages), drawn on Canvas where needed."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from . import theme as T


class Panel(tk.Frame):
    """A flat panel with a hairline border."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=T.PANEL, highlightthickness=1, highlightbackground=T.LINE, highlightcolor=T.LINE, bd=0)


class AutoLabel(tk.Label):
    """Left-aligned label that re-wraps its text to whatever width it is given."""

    def __init__(self, master: tk.Misc, text: str = "", **kw) -> None:
        kw.setdefault("justify", "left")
        kw.setdefault("anchor", "w")
        kw.setdefault("wraplength", T.px(480))
        super().__init__(master, text=text, **kw)
        self.bind("<Configure>", self._fit)

    def _fit(self, event) -> None:
        width = max(T.px(60), int(event.width) - 2)
        if abs(int(float(self.cget("wraplength"))) - width) > 2:
            self.configure(wraplength=width)


class Btn(tk.Label):
    """Flat button. Styles: 'solid' (brass fill), 'outline' (brass border), 'ghost' (quiet)."""

    #            text         fill        hover text   hover fill    border
    _STYLES = {
        "solid": (T.INK, T.BRASS, T.INK, T.BRASS_HI, T.BRASS),
        "outline": (T.BRASS, T.PANEL, T.INK, T.BRASS, T.BRASS_LO),
        "ghost": (T.CREAM, T.RAISED, T.CREAM, T.LINE, T.LINE),
    }

    def __init__(self, master: tk.Misc, text: str, command: Optional[Callable[[], object]] = None,
                 style: str = "outline", width: int = 0) -> None:
        fg, bg, _hfg, _hbg, border = self._STYLES[style]
        super().__init__(master, text=text, fg=fg, bg=bg, font="ix9.btn", cursor="hand2", width=width,
                         padx=T.px(14), pady=T.px(6), highlightthickness=1,
                         highlightbackground=border, highlightcolor=border)
        self._style = style
        self._command = command
        self._enabled = True
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _event) -> None:
        if self._enabled:
            _fg, _bg, hfg, hbg, _border = self._STYLES[self._style]
            self.configure(fg=hfg, bg=hbg)

    def _on_leave(self, _event) -> None:
        if self._enabled:
            fg, bg, _hfg, _hbg, _border = self._STYLES[self._style]
            self.configure(fg=fg, bg=bg)

    def _on_release(self, event) -> None:
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if self._enabled and inside and self._command:
            self._command()

    def set_text(self, text: str) -> None:
        self.configure(text=text)

    def enable(self, flag: bool) -> None:
        self._enabled = bool(flag)
        fg, bg, _hfg, _hbg, border = self._STYLES[self._style]
        if flag:
            self.configure(fg=fg, bg=bg, cursor="hand2", highlightbackground=border, highlightcolor=border)
        else:
            self.configure(fg=T.MUTED, bg=T.PANEL, cursor="arrow", highlightbackground=T.LINE, highlightcolor=T.LINE)


class Ladder(tk.Canvas):
    """LED-ladder level meter, like the meters on an amp or a mixer."""

    def __init__(self, master: tk.Misc, segments: int = 26, height: int = 14) -> None:
        super().__init__(master, height=T.px(height), bg=T.PANEL, highlightthickness=0, bd=0)
        self._segments = segments
        self._fraction = 0.0
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        if abs(fraction - self._fraction) > 0.004:
            self._fraction = fraction
            self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 40:
            return
        gap = T.px(2)
        count = self._segments
        seg = (width - gap * (count - 1)) / count
        lit = int(round(self._fraction * count))
        for i in range(count):
            position = (i + 1) / count
            if i < lit:
                color = T.BRASS if position <= 0.65 else (T.ORANGE if position <= 0.85 else T.RED)
            else:
                color = T.LED_OFF
            x0 = i * (seg + gap)
            self.create_rectangle(x0, 0, x0 + seg, height, fill=color, width=0)


class Knob(tk.Canvas):
    """The big dial. Twelve ticks, 0 to 11. It sweeps to its new value when the level changes."""

    TICKS = 12

    def __init__(self, master: tk.Misc, size: int = 132) -> None:
        self._size = T.px(size)
        super().__init__(master, width=self._size, height=self._size, bg=T.PANEL, highlightthickness=0, bd=0)
        self._shown = 0.0
        self._target = 0.0
        self._job: Optional[str] = None
        self._draw(0.0)

    def set_level(self, level: float) -> None:
        self._target = float(max(0, min(self.TICKS - 1, level)))
        if self._job is None:
            self._step()

    def _step(self) -> None:
        diff = self._target - self._shown
        if abs(diff) < 0.05:
            self._shown = self._target
            self._job = None
            self._draw(self._shown)
            return
        self._shown += diff * 0.22
        self._draw(self._shown)
        self._job = self.after(16, self._step)

    def _draw(self, level: float) -> None:
        self.delete("all")
        size = self._size
        centre = size / 2
        n = self.TICKS
        # ticks: lit up to the current level, the last one (11) is red
        for i in range(n):
            angle = math.radians(-135 + 270 * i / (n - 1))
            sin, cos = math.sin(angle), math.cos(angle)
            lit = i <= level + 0.01
            color = (T.RED if i == n - 1 else T.BRASS) if lit else T.LED_OFF
            self.create_line(centre + sin * size * 0.40, centre - cos * size * 0.40,
                             centre + sin * size * 0.48, centre - cos * size * 0.48,
                             fill=color, width=T.px(3), capstyle="round")
        body = size * 0.33
        self.create_oval(centre - body, centre - body, centre + body, centre + body,
                         fill=T.BG, outline=T.BRASS, width=T.px(3))
        inner = size * 0.26
        self.create_oval(centre - inner, centre - inner, centre + inner, centre + inner,
                         fill=T.RAISED, outline=T.LINE, width=1)
        angle = math.radians(-135 + 270 * max(0.0, min(level, n - 1)) / (n - 1))
        self.create_line(centre, centre, centre + math.sin(angle) * size * 0.25, centre - math.cos(angle) * size * 0.25,
                         fill=T.RED, width=T.px(3), capstyle="round")
        cap = size * 0.045
        self.create_oval(centre - cap, centre - cap, centre + cap, centre + cap, fill=T.BRASS, width=0)


class Switch(tk.Canvas):
    """On/off switch. `command(wanted_state)` may return False to refuse the click."""

    def __init__(self, master: tk.Misc, command: Optional[Callable[[bool], object]] = None) -> None:
        self._w, self._h = T.px(46), T.px(24)
        super().__init__(master, width=self._w, height=self._h, bg=T.PANEL, highlightthickness=0, bd=0, cursor="hand2")
        self._on = False
        self._command = command
        self.bind("<Button-1>", self._click)
        self._draw()

    def get(self) -> bool:
        return self._on

    def set(self, on: bool) -> None:
        if bool(on) != self._on:
            self._on = bool(on)
            self._draw()

    def _click(self, _event) -> None:
        wanted = not self._on
        if self._command is not None and self._command(wanted) is False:
            return
        self.set(wanted)

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._w, self._h
        track = T.BRASS if self._on else T.LINE
        self.create_oval(0, 0, h, h, fill=track, width=0)
        self.create_oval(w - h, 0, w, h, fill=track, width=0)
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=track, width=0)
        pad = T.px(3)
        d = h - 2 * pad
        x = (w - pad - d) if self._on else pad
        self.create_oval(x, pad, x + d, pad + d, fill=(T.INK if self._on else T.MUTED), width=0)


class Pips(tk.Canvas):
    """Three small lamps showing how much a tweak matters (1-3)."""

    def __init__(self, master: tk.Misc, level: int = 1, total: int = 3) -> None:
        d, gap = T.px(8), T.px(4)
        super().__init__(master, width=total * d + (total - 1) * gap, height=d, bg=T.PANEL, highlightthickness=0, bd=0)
        for i in range(total):
            x = i * (d + gap)
            self.create_oval(x, 0, x + d, d, fill=(T.BRASS if i < level else T.LED_OFF), width=0)


class Lamp(tk.Canvas):
    """Status lamp in the header."""

    def __init__(self, master: tk.Misc, bg: str = T.BG) -> None:
        d = T.px(10)
        super().__init__(master, width=d, height=d, bg=bg, highlightthickness=0, bd=0)
        self._d = d
        self.set(T.GREEN)

    def set(self, color: str) -> None:
        self.delete("all")
        self.create_oval(0, 0, self._d, self._d, fill=color, width=0)


class ScrollFrame(tk.Frame):
    """A vertically scrolling area. Put children into `.inner`. The mouse wheel is routed by the app."""

    def __init__(self, master: tk.Misc, bg: str = T.PANEL) -> None:
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=T.px(24))
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Ix9.Vertical.TScrollbar")
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))

    def wheel(self, delta: int) -> None:
        if tuple(self.canvas.yview()) == (0.0, 1.0):
            return  # everything already fits
        steps = max(1, abs(int(delta)) // 40)
        self.canvas.yview_scroll(-steps if delta > 0 else steps, "units")

    def clear(self) -> None:
        for child in list(self.inner.winfo_children()):
            child.destroy()
        self.canvas.yview_moveto(0)


class LogView(tk.Frame):
    """Read-only activity console. Every change the app makes is written here."""

    COLORS = {"info": T.CREAM, "ok": T.GREEN, "warn": T.ORANGE, "err": T.RED, "dim": T.MUTED, "time": T.BRASS_LO}

    def __init__(self, master: tk.Misc, lines: int = 7) -> None:
        super().__init__(master, bg=T.PANEL, highlightthickness=1, highlightbackground=T.LINE, highlightcolor=T.LINE)
        self.text = tk.Text(self, height=lines, bg=T.PANEL, fg=T.CREAM, insertbackground=T.CREAM, bd=0,
                            highlightthickness=0, wrap="word", font="ix9.mono", state="disabled",
                            padx=T.px(10), pady=T.px(8), relief="flat")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview, style="Ix9.Vertical.TScrollbar")
        self.text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        for tag, color in self.COLORS.items():
            self.text.tag_configure(tag, foreground=color)

    def add(self, message: str, level: str = "info") -> None:
        tag = level if level in self.COLORS else "info"
        self.text.configure(state="normal")
        self.text.insert("end", time.strftime("%H:%M:%S") + "  ", "time")
        self.text.insert("end", message + "\n", tag)
        total = int(self.text.index("end-1c").split(".")[0])
        if total > 600:
            self.text.delete("1.0", f"{total - 500}.0")
        self.text.see("end")
        self.text.configure(state="disabled")
