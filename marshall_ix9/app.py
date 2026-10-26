"""The Marshall IX9 window. Long jobs run in a worker thread; the UI only changes on the main thread."""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, Optional

from . import APP_NAME, __version__
from .core import power, sysinfo
from .core import tweaks as tw
from .core import winutil as wu
from .ui import theme as T
from .ui.pages import AppsPage, CleanerPage, DashboardPage, Page, SafetyPage, TweaksPage
from .ui.widgets import Btn, Lamp, LogView, ScrollFrame

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]


def resource_path(relative: str) -> str:
    """Find a bundled file, both when run from source and from the PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def write_error_log(text: str) -> str:
    path = os.path.join(wu.data_dir(), "error.log")
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}\n")
    except OSError:
        pass
    return path


def _enable_dpi_awareness() -> None:
    if not wu.IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _style_titlebar(window: tk.Misc) -> None:
    """Dark title bar on Windows 10/11 (and a matching caption colour on Windows 11). Purely cosmetic."""
    if not wu.IS_WIN:
        return
    try:
        from ctypes import wintypes

        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dwm = ctypes.WinDLL("dwmapi")
        fn = dwm.DwmSetWindowAttribute
        fn.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

        def colorref(hex_color: str) -> int:
            r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
            return r | (g << 8) | (b << 16)

        dark = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20 on new builds, 19 on older)
            if fn(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        for attribute, color in ((35, T.SIDEBAR), (36, T.CREAM)):  # caption + text colour (Windows 11)
            value = ctypes.c_int(colorref(color))
            fn(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


class NavItem(tk.Frame):
    """Sidebar entry: brass bar on the left when active."""

    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None]) -> None:
        super().__init__(master, bg=T.SIDEBAR, cursor="hand2")
        self._active = False
        self.bar = tk.Frame(self, bg=T.SIDEBAR, width=T.px(3))
        self.bar.pack(side="left", fill="y")
        self.label = tk.Label(self, text=text, font="ix9.nav", fg=T.MUTED, bg=T.SIDEBAR, anchor="w",
                              padx=T.px(18), pady=T.px(11))
        self.label.pack(side="left", fill="x", expand=True)
        for widget in (self, self.label):
            widget.bind("<Button-1>", lambda _e: command())
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _paint(self, hover: bool) -> None:
        if self._active:
            bg, fg, bar = T.RAISED, T.CREAM, T.BRASS
        else:
            bg, fg, bar = (T.PANEL if hover else T.SIDEBAR), (T.CREAM if hover else T.MUTED), T.SIDEBAR
        self.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg)
        self.bar.configure(bg=bar)

    def _enter(self, _event) -> None:
        self._paint(True)

    def _leave(self, _event) -> None:
        self._paint(False)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._paint(False)


class App(tk.Tk):
    NAV = (("dashboard", "Dashboard"), ("tweaks", "Tweaks"), ("cleaner", "Pembersih"),
           ("apps", "Aplikasi"), ("safety", "Keamanan"))

    def __init__(self) -> None:
        _enable_dpi_awareness()
        super().__init__()
        self.withdraw()  # no white flash while the window is being built
        T.init(self)
        self.title(f"{APP_NAME} - PC Optimizer")
        self.configure(bg=T.BG)
        self._size_window()
        self._set_icon()
        self._style_scrollbar()

        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False
        self.opt_restore = tk.BooleanVar(master=self, value=True)
        self.backup = wu.BackupStore()
        self.tweaks = tw.build_tweaks(self.backup)
        self.pages: Dict[str, Page] = {}
        self.nav_items: Dict[str, NavItem] = {}
        self.current = ""
        self._logo: Optional[tk.PhotoImage] = None

        self._build()
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.after(80, self._pump)
        self.after(600, self._tick)

        self.deiconify()
        self.update_idletasks()
        _style_titlebar(self)
        self.show("dashboard")

        self.log("Marshall IX9 siap. Semua perubahan dicatat di sini dan bisa dikembalikan.", "info")
        if wu.IS_WIN and not wu.is_admin():
            self.log("Belum berjalan sebagai Administrator: sebagian tweak akan dilewati.", "warn")
        self._load_info()
        self.run_task("baca status", self.snapshot, self.on_snapshot, quiet=True)

    # ------------------------------------------------------------------ window setup
    def _size_window(self) -> None:
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(T.px(1080), screen_w - T.px(60))
        height = min(T.px(760), screen_h - T.px(90))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(T.px(920), width), min(T.px(640), height))

    def _set_icon(self) -> None:
        icon = resource_path("assets/icon.ico")
        if wu.IS_WIN and os.path.exists(icon):
            try:
                self.iconbitmap(icon)
            except tk.TclError:
                pass

    def _style_scrollbar(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
            style.configure("Ix9.Vertical.TScrollbar", background=T.LINE, troughcolor=T.PANEL, bordercolor=T.PANEL,
                            lightcolor=T.LINE, darkcolor=T.LINE, arrowcolor=T.MUTED, relief="flat")
            style.map("Ix9.Vertical.TScrollbar", background=[("active", T.BRASS_LO), ("pressed", T.BRASS)])
            style.layout("Ix9.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
                "sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        except tk.TclError:
            pass  # default scrollbar look is fine

    def _load_logo(self) -> Optional[tk.PhotoImage]:
        wanted = T.px(72)
        best = None
        for size in (48, 64, 96, 128, 192, 256, 384):
            path = resource_path(f"assets/logo_{size}.png")
            if os.path.exists(path) and (best is None or abs(size - wanted) < abs(best[0] - wanted)):
                best = (size, path)
        if best is None:
            return None
        try:
            return tk.PhotoImage(file=best[1])
        except tk.TclError:
            return None

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        side = tk.Frame(self, bg=T.SIDEBAR, width=T.px(228))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        brand = tk.Frame(side, bg=T.SIDEBAR)
        brand.pack(fill="x", padx=T.px(20), pady=(T.px(24), T.px(22)))
        self._logo = self._load_logo()
        if self._logo is not None:
            tk.Label(brand, image=self._logo, bg=T.SIDEBAR).pack(anchor="w")
        tk.Label(brand, text="Marshall", font="ix9.body", fg=T.MUTED, bg=T.SIDEBAR).pack(anchor="w", pady=(T.px(10), 0))
        tk.Label(brand, text="IX9", font="ix9.hero", fg=T.BRASS, bg=T.SIDEBAR).pack(anchor="w")
        tk.Label(brand, text=f"PC optimizer v{__version__}", font="ix9.small", fg=T.MUTED, bg=T.SIDEBAR).pack(anchor="w")

        for key, label in self.NAV:
            item = NavItem(side, label, lambda k=key: self.show(k))
            item.pack(fill="x")
            self.nav_items[key] = item

        foot = tk.Frame(side, bg=T.SIDEBAR)
        foot.pack(side="bottom", fill="x", padx=T.px(20), pady=T.px(18))
        admin_ok = wu.is_admin()
        tk.Label(foot, text="Administrator: ya" if admin_ok else "Administrator: tidak", font="ix9.small",
                 fg=T.GREEN if admin_ok else T.ORANGE, bg=T.SIDEBAR, anchor="w").pack(fill="x")
        self.power_label = tk.Label(foot, text="", font="ix9.small", fg=T.MUTED, bg=T.SIDEBAR, anchor="w")
        self.power_label.pack(fill="x", pady=(T.px(2), 0))

        main = tk.Frame(self, bg=T.BG)
        main.pack(side="right", fill="both", expand=True)

        header = tk.Frame(main, bg=T.BG)
        header.pack(fill="x", padx=T.px(26), pady=(T.px(22), T.px(12)))
        titles = tk.Frame(header, bg=T.BG)
        titles.pack(side="left")
        self.title_label = tk.Label(titles, text="", font="ix9.title", fg=T.CREAM, bg=T.BG, anchor="w")
        self.title_label.pack(anchor="w")
        self.blurb_label = tk.Label(titles, text="", font="ix9.body", fg=T.MUTED, bg=T.BG, anchor="w")
        self.blurb_label.pack(anchor="w")
        status = tk.Frame(header, bg=T.BG)
        status.pack(side="right", anchor="n")
        self.lamp = Lamp(status)
        self.lamp.pack(side="left", padx=(0, T.px(8)))
        self.status_label = tk.Label(status, text="Siap", font="ix9.bodyb", fg=T.CREAM, bg=T.BG)
        self.status_label.pack(side="left")
        self.uptime_label = tk.Label(header, text="", font="ix9.small", fg=T.MUTED, bg=T.BG)
        self.uptime_label.pack(side="right", anchor="n", padx=(0, T.px(20)))

        if wu.IS_WIN and not wu.is_admin():
            banner = tk.Frame(main, bg=T.RAISED, highlightthickness=1, highlightbackground=T.LINE)
            banner.pack(fill="x", padx=T.px(26), pady=(0, T.px(10)))
            tk.Label(banner, text="Belum Administrator, jadi tweak sistem akan dilewati.", font="ix9.body",
                     fg=T.ORANGE, bg=T.RAISED).pack(side="left", padx=T.px(14), pady=T.px(8))
            Btn(banner, "Jalankan sebagai admin", self.relaunch_as_admin, style="outline").pack(side="right", padx=T.px(10), pady=T.px(6))

        console = tk.Frame(main, bg=T.BG)  # packed before the content so it never gets squeezed out
        console.pack(side="bottom", fill="x", padx=T.px(26), pady=(T.px(10), T.px(18)))
        tk.Label(console, text="Catatan aktivitas", font="ix9.small", fg=T.MUTED, bg=T.BG).pack(anchor="w", pady=(0, T.px(4)))
        self.console = LogView(console)
        self.console.pack(fill="x")

        content = tk.Frame(main, bg=T.BG)
        content.pack(fill="both", expand=True, padx=T.px(26))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        for key, cls in (("dashboard", DashboardPage), ("tweaks", TweaksPage), ("cleaner", CleanerPage),
                         ("apps", AppsPage), ("safety", SafetyPage)):
            page = cls(content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

    @property
    def dashboard(self) -> DashboardPage:
        return self.pages["dashboard"]  # type: ignore[return-value]

    def show(self, key: str) -> None:
        page = self.pages[key]
        page.tkraise()
        self.current = key
        for name, item in self.nav_items.items():
            item.set_active(name == key)
        self.title_label.configure(text=page.title)
        self.blurb_label.configure(text=page.blurb)
        page.on_show()

    # ------------------------------------------------------------------ threads and messages
    def log(self, message: str, level: str = "info") -> None:
        """Safe to call from any thread."""
        self.queue.put(("log", message, level))

    def run_task(self, label: str, fn: Callable[[], object], done: Optional[Callable[[object], None]] = None,
                 quiet: bool = False) -> bool:
        """Run `fn` in a worker thread, then call `done(result)` on the UI thread. False if already busy."""
        if self.busy:
            if not quiet:
                self.log("Masih ada proses yang berjalan, tunggu sebentar.", "warn")
            return False
        self.busy = True
        self._set_working(True)

        def work() -> None:
            result = None
            try:
                result = fn()
            except Exception as exc:
                self.log(f"Error pada '{label}': {exc}", "err")
                write_error_log(traceback.format_exc())
            self.queue.put(("done", done, result))

        threading.Thread(target=work, daemon=True).start()
        return True

    def _pump(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.console.add(item[1], item[2])
                elif kind == "call":
                    item[1]()
                elif kind == "done":
                    self.busy = False
                    self._set_working(False)
                    if item[1] is not None:
                        try:
                            item[1](item[2])
                        except Exception as exc:
                            self.console.add(f"Error di tampilan: {exc}", "err")
                            write_error_log(traceback.format_exc())
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def _set_working(self, working: bool) -> None:
        self.lamp.set(T.ORANGE if working else T.GREEN)
        self.status_label.configure(text="Bekerja..." if working else "Siap")

    def report_callback_exception(self, exc, val, tb) -> None:  # Tk calls this for errors inside callbacks
        text = "".join(traceback.format_exception(exc, val, tb))
        write_error_log(text)
        try:
            self.console.add(f"Error di tampilan: {val}", "err")
        except Exception:
            pass

    def _on_wheel(self, event) -> None:
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while widget is not None:
            if
