"""`MarshallIX9.exe --selftest result.txt` - a read-only health check run by the GitHub build.

It changes nothing on the computer: it only reads settings, scans folders (without deleting)
and opens the window once to prove the packaged app starts.
"""
from __future__ import annotations

import os
import tempfile
from typing import Callable, List


def run_selftest(argv: List[str]) -> int:
    out_path = None
    if "--selftest" in argv:
        index = argv.index("--selftest")
        if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            out_path = argv[index + 1]

    lines: List[str] = []
    failures: List[str] = []

    def check(name: str, fn: Callable[[], object]) -> None:
        try:
            lines.append(f"[ok]   {name}: {fn()}")
        except Exception as exc:  # report everything, stop at nothing
            failures.append(name)
            lines.append(f"[FAIL] {name}: {exc!r}")

    def tk_probe() -> str:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        version = root.tk.call("info", "patchlevel")
        root.destroy()
        return f"Tk {version}"

    def assets() -> str:
        from .app import resource_path

        needed = ["assets/icon.ico", "assets/logo_64.png", "assets/logo_96.png"]
        missing = [name for name in needed if not os.path.exists(resource_path(name))]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return "icon dan logo ada"

    def tweak_states() -> str:
        from .core import tweaks as tw
        from .core import winutil as wu

        backup = wu.BackupStore(os.path.join(tempfile.mkdtemp(), "selftest-backup.json"))
        states = tw.snapshot(tw.build_tweaks(backup))
        return ", ".join(f"{key}={value}" for key, value in states.items())

    def power_state() -> str:
        from .core import power

        return f"scheme={power.active_scheme()} overlay={power.overlay_get()} ac={power.on_ac()}"

    def device() -> str:
        from .core import sysinfo

        return " | ".join(f"{label}: {value}" for label, value in sysinfo.collect())

    def cleaner_scan() -> str:
        from .core import cleaner

        return ", ".join(f"{cat.id}={cleaner.format_size(cleaner.scan(cat)[0])}" for cat in cleaner.CATEGORIES)

    def apps() -> str:
        from .core import processes, startup

        return f"{len(processes.list_user_apps())} aplikasi, {len(startup.list_items())} item startup"

    def window() -> str:
        from .app import App

        app = App()
        try:
            for key in ("tweaks", "cleaner", "apps", "safety", "dashboard"):
                app.show(key)
            app.update()
        finally:
            app.destroy()
        return "jendela terbuka dan semua halaman tampil"

    check("tkinter", tk_probe)
    check("assets", assets)
    check("tweak status", tweak_states)
    check("power", power_state)
    check("device", device)
    check("cleaner (scan saja)", cleaner_scan)
    check("apps + startup", apps)
    check("window", window)

    lines.append("RESULT: " + ("OK" if not failures else "GAGAL -> " + ", ".join(failures)))
    text = "\n".join(lines)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0 if not failures else 1
