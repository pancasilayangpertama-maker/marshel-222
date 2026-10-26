"""The five pages of the window. Each page talks to the App only through a few small methods."""
from __future__ import annotations

import tkinter as tk
from typing import Dict, List, Optional, Tuple

from ..core import cleaner, processes, startup
from ..core import tweaks as tw
from ..core import winutil as wu
from . import theme as T
from .widgets import AutoLabel, Btn, Knob, Ladder, Panel, Pips, ScrollFrame, Switch


class Page(tk.Frame):
    title = ""
    blurb = ""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, bg=T.BG)
        self.app = app

    def on_show(self) -> None:
        """Called every time the page becomes visible."""

    def on_states(self, states: Dict[str, Optional[bool]]) -> None:
        """Called whenever the tweak states were re-read."""


def _check(master: tk.Misc, text: str, variable: tk.BooleanVar, bg: str, fg: str = T.MUTED) -> tk.Checkbutton:
    return tk.Checkbutton(master, text=text, variable=variable, font="ix9.small", fg=fg, bg=bg,
                          activebackground=bg, activeforeground=T.CREAM, selectcolor=T.RAISED,
                          highlightthickness=0, bd=0, anchor="w", cursor="hand2")


# =============================================================================== dashboard


class DashboardPage(Page):
    title = "Dashboard"
    blurb = "Kondisi laptop sekarang dan tombol Boost satu klik."

    NOTES = (
        "Batas laptop tipis adalah panas, bukan software. Dicas dan pakai cooling pad sudah langkah paling efektif.",
        "Kalau ada di modelmu, buka MyASUS lalu atur Fan Mode / Performance Mode ke Performance. Itu yang menentukan batas daya CPU.",
        "Update driver grafis lewat MyASUS atau situs resmi Intel / AMD, lalu tutup aplikasi berat di tab Aplikasi sebelum main.",
    )

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, app)
        for column in range(3):
            self.columnconfigure(column, weight=1, uniform="stat")
        self.rowconfigure(2, weight=1)

        hero = Panel(self)
        hero.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, T.px(12)))
        hero.columnconfigure(1, weight=1)
        self.knob = Knob(hero)
        self.knob.grid(row=0, column=0, padx=T.px(22), pady=T.px(18))
        body = tk.Frame(hero, bg=T.PANEL)
        body.grid(row=0, column=1, sticky="ew", padx=(0, T.px(20)), pady=T.px(16))
        self.level_title = tk.Label(body, text="Belum ada tweak aktif", font="ix9.title", fg=T.CREAM, bg=T.PANEL, anchor="w")
        self.level_title.pack(fill="x")
        AutoLabel(body, text=("Boost menerapkan tweak rekomendasi untuk laptop tipis yang selalu dicas. "
                              "Semuanya di-backup dulu dan bisa dikembalikan kapan saja."),
                  font="ix9.body", fg=T.MUTED, bg=T.PANEL).pack(fill="x", pady=(T.px(4), T.px(12)))
        buttons = tk.Frame(body, bg=T.PANEL)
        buttons.pack(anchor="w")
        Btn(buttons, "Boost sekarang", app.boost, style="solid").pack(side="left")
        Btn(buttons, "Kembalikan semua", app.restore_all, style="ghost").pack(side="left", padx=(T.px(8), 0))
        _check(body, "Buat restore point Windows dulu (disarankan)", app.opt_restore, T.PANEL).pack(anchor="w", pady=(T.px(12), 0))

        self.cpu = self._stat(1, 0, "Prosesor")
        self.ram = self._stat(1, 1, "Memori")
        self.disk = self._stat(1, 2, "Penyimpanan")

        info = Panel(self)
        info.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(0, T.px(6)))
        tk.Label(info, text="Perangkat", font="ix9.h2", fg=T.CREAM, bg=T.PANEL).pack(anchor="w", padx=T.px(16), pady=(T.px(14), T.px(6)))
        self.info_body = tk.Frame(info, bg=T.PANEL)
        self.info_body.pack(fill="x", padx=T.px(16), pady=(0, T.px(14)))

        notes = Panel(self)
        notes.grid(row=2, column=2, sticky="nsew", padx=(T.px(6), 0))
        tk.Label(notes, text="Catatan laptop tipis", font="ix9.h2", fg=T.CREAM, bg=T.PANEL).pack(anchor="w", padx=T.px(16), pady=(T.px(14), T.px(6)))
        for text in self.NOTES:
            AutoLabel(notes, text=text, font="ix9.small", fg=T.MUTED, bg=T.PANEL).pack(fill="x", padx=T.px(16), pady=(0, T.px(8)))

    def _stat(self, row: int, column: int, label: str) -> Tuple[tk.Label, Ladder, AutoLabel]:
        card = Panel(self)
        card.grid(row=row, column=column, sticky="nsew", pady=(0, T.px(12)),
                  padx=(0 if column == 0 else T.px(6), 0 if column == 2 else T.px(6)))
        tk.Label(card, text=label, font="ix9.small", fg=T.MUTED, bg=T.PANEL).pack(anchor="w", padx=T.px(16), pady=(T.px(14), 0))
        value = tk.Label(card, text="-", font="ix9.big", fg=T.CREAM, bg=T.PANEL)
        value.pack(anchor="w", padx=T.px(16))
        ladder = Ladder(card)
        ladder.pack(fill="x", padx=T.px(16), pady=(T.px(8), T.px(6)))
        sub = AutoLabel(card, text="", font="ix9.small", fg=T.MUTED, bg=T.PANEL)
        sub.pack(fill="x", padx=T.px(16), pady=(0, T.px(14)))
        return value, ladder, sub

    # -- updates from the app ---------------------------------------------------
    def set_info(self, pairs: List[Tuple[str, str]]) -> None:
        for child in list(self.info_body.winfo_children()):
            child.destroy()
        self.info_body.columnconfigure(1, weight=1)
        for row, (label, value) in enumerate(pairs):
            tk.Label(self.info_body, text=label, font="ix9.small", fg=T.MUTED, bg=T.PANEL, anchor="w").grid(
                row=row, column=0, sticky="nw", padx=(0, T.px(18)), pady=T.px(3))
            AutoLabel(self.info_body, text=value, font="ix9.body", fg=T.CREAM, bg=T.PANEL).grid(
                row=row, column=1, sticky="ew", pady=T.px(3))
            if label == "Prosesor":
                self.cpu[2].configure(text=value)

    def update_live(self, cpu: float, ram: float, ram_text: str, disk: float, disk_text: str) -> None:
        self.cpu[0].configure(text=f"{cpu:.0f}%")
        self.cpu[1].set(cpu / 100)
        self.ram[0].configure(text=f"{ram:.0f}%")
        self.ram[1].set(ram / 100)
        self.ram[2].configure(text=ram_text)
        self.disk[0].configure(text=f"{disk:.0f}%")
        self.disk[1].set(disk / 100)
        self.disk[2].configure(text=disk_text)

    def on_states(self, states: Dict[str, Optional[bool]]) -> None:
        wanted = [t for t in self.app.tweaks if t.recommended]
        active = sum(1 for t in wanted if states.get(t.id))
        total = len(wanted)
        self.knob.set_level(round(active / total * 11) if total else 0)
        if active == 0:
            text = "Belum ada tweak aktif"
        elif active == total:
            text = f"Semua {total} tweak aktif: level 11"
        else:
            text = f"{active} dari {total} tweak aktif"
        self.level_title.configure(text=text)


# =============================================================================== tweaks


class TweaksPage(Page):
    title = "Tweaks"
    blurb = "Nyalakan atau matikan satu per satu. Titik di kanan menunjukkan seberapa besar efeknya."

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, app)
        panel = Panel(self)
        panel.pack(fill="both", expand=True)
        self.scroll = ScrollFrame(panel)
        self.scroll.pack(fill="both", expand=True, padx=1, pady=1)
        self.switches: Dict[str, Switch] = {}
        self.state_labels: Dict[str, tk.Label] = {}
        for index, tweak in enumerate(app.tweaks):
            self._row(tweak, first=(index == 0))

    def _row(self, tweak: tw.Tweak, first: bool) -> None:
        inner = self.scroll.inner
        if not first:
            tk.Frame(inner, bg=T.LINE, height=1).pack(fill="x")
        row = tk.Frame(inner, bg=T.PANEL)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)

        text = tk.Frame(row, bg=T.PANEL)
        text.grid(row=0, column=0, sticky="ew", padx=T.px(18), pady=T.px(14))
        tk.Label(text, text=tweak.title, font="ix9.h2", fg=T.CREAM, bg=T.PANEL, anchor="w").pack(fill="x")
        AutoLabel(text, text=tweak.desc, font="ix9.body", fg=T.MUTED, bg=T.PANEL).pack(fill="x", pady=(T.px(3), 0))
        notes = []
        if tweak.ac_only:
            notes.append("Berlaku saat dicas.")
        if tweak.admin:
            notes.append("Perlu Administrator.")
        if tweak.reboot:
            notes.append("Aktif penuh setelah restart.")
        if tweak.note:
            notes.append(tweak.note)
        if notes:
            tk.Label(text, text="  ".join(notes), font="ix9.small", fg=T.BRASS_LO, bg=T.PANEL, anchor="w").pack(fill="x", pady=(T.px(4), 0))

        control = tk.Frame(row, bg=T.PANEL)
        control.grid(row=0, column=1, padx=T.px(18))
        Pips(control, tweak.impact).pack(anchor="e", pady=(0, T.px(8)))
        switch = Switch(control, command=lambda want, t=tweak: self._toggle(t, want))
        switch.pack(anchor="e")
        label = tk.Label(control, text="", font="ix9.small", fg=T.MUTED, bg=T.PANEL)
        label.pack(anchor="e", pady=(T.px(4), 0))
        self.switches[tweak.id] = switch
        self.state_labels[tweak.id] = label

    def _toggle(self, tweak: tw.Tweak, want: bool) -> bool:
        def job():
            if want:
                tweak.apply(self.app.log)
            else:
                tweak.undo(self.app.log)
            return self.app.snapshot()

        return self.app.run_task(tweak.title, job, self.app.on_snapshot)

    def on_states(self, states: Dict[str, Optional[bool]]) -> None:
        for tweak_id, switch in self.switches.items():
            state = states.get(tweak_id)
            switch.set(bool(state))
            label = self.state_labels[tweak_id]
            if state is None:
                label.configure(text="tidak terbaca", fg=T.MUTED)
            elif state:
                label.configure(text="aktif", fg=T.BRASS)
            else:
                label.configure(text="mati", fg=T.MUTED)


# =============================================================================== cleaner


class CleanerPage(Page):
    title = "Pembersih"
    blurb = "Hapus file sampah yang aman dihapus. Pindai dulu, lalu bersihkan."

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, app)
        panel = Panel(self)
        panel.pack(fill="x")
        self.checks: Dict[str, tk.BooleanVar] = {}
        self.sizes: Dict[str, tk.Label] = {}
        for index, cat in enumerate(cleaner.CATEGORIES):
            if index:
                tk.Frame(panel, bg=T.LINE, height=1).pack(fill="x")
            row = tk.Frame(panel, bg=T.PANEL)
            row.pack(fill="x")
            row.columnconfigure(1, weight=1)
            var = tk.BooleanVar(master=self, value=True)
            self.checks[cat.id] = var
            tk.Checkbutton(row, variable=var, bg=T.PANEL, activebackground=T.PANEL, selectcolor=T.RAISED,
                           fg=T.BRASS, activeforeground=T.BRASS, highlightthickness=0, bd=0, cursor="hand2").grid(
                row=0, column=0, rowspan=2, padx=(T.px(14), T.px(4)))
            tk.Label(row, text=cat.title, font="ix9.h2", fg=T.CREAM, bg=T.PANEL, anchor="w").grid(
                row=0, column=1, sticky="ew", pady=(T.px(12), 0))
            AutoLabel(row, text=cat.desc, font="ix9.body", fg=T.MUTED, bg=T.PANEL).grid(
                row=1, column=1, sticky="ew", pady=(0, T.px(12)))
            size = tk.Label(row, text="belum dipindai", font="ix9.small", fg=T.MUTED, bg=T.PANEL, anchor="e")
            size.grid(row=0, column=2, rowspan=2, padx=T.px(16))
            self.sizes[cat.id] = size

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", pady=(T.px(14), 0))
        Btn(bar, "Pindai", self.scan, style="outline").pack(side="left")
        Btn(bar, "Bersihkan yang dicentang", self.clean, style="solid").pack(side="left", padx=(T.px(8), 0))
        self.recent = tk.BooleanVar(master=self, value=False)
        _check(bar, "Termasuk file yang lebih baru dari 24 jam (tidak disarankan)", self.recent, T.BG).pack(side="left", padx=(T.px(16), 0))
        self.summary = tk.Label(self, text="", font="ix9.body", fg=T.MUTED, bg=T.BG, anchor="w")
        self.summary.pack(fill="x", pady=(T.px(14), 0))

    def scan(self) -> None:
        include = bool(self.recent.get())

        def job():
            return {cat.id: cleaner.scan(cat, include) for cat in cleaner.CATEGORIES}

        self.app.run_task("pindai", job, self._show)

    def clean(self) -> None:
        chosen = [cat for cat in cleaner.CATEGORIES if self.checks[cat.id].get()]
        if not chosen:
            self.app.log("Belum ada kategori yang dicentang", "warn")
            return
        if not self.app.confirm("Bersihkan", "Hapus file di kategori yang dicentang?\n\n"
                                "File yang dihapus tidak bisa dikembalikan (Recycle Bin dikosongkan permanen)."):
            return
        include = bool(self.recent.get())

        def job():
            total = 0
            for cat in chosen:
                freed, deleted, skipped = cleaner.clean(cat, include)
                total += freed
                self.app.log(f"{cat.title}: {cleaner.format_size(freed)} dibersihkan ({deleted} file, {skipped} dilewati karena sedang dipakai)",
                             "ok" if (deleted or freed) else "dim")
            self.app.log(f"Total ruang yang kembali: {cleaner.format_size(total)}", "ok")
            return {cat.id: cleaner.scan(cat, include) for cat in cleaner.CATEGORIES}

        self.app.run_task("bersihkan", job, self._show)

    def _show(self, result: Optional[Dict[str, Tuple[int, int]]]) -> None:
        if not result:
            return
        total = 0
        for cat in cleaner.CATEGORIES:
            size, files = result.get(cat.id, (0, 0))
            total += size
            text = "kosong" if size == 0 and files == 0 else f"{cleaner.format_size(size)} ({files} file)"
            self.sizes[cat.id].configure(text=text, fg=T.CREAM if size else T.MUTED)
        self.summary.configure(text=f"Bisa dibersihkan sekarang: {cleaner.format_size(total)}", fg=T.CREAM if total else T.MUTED)
        self.app.log(f"Pindai selesai: {cleaner.format_size(total)} bisa dibersihkan", "info")


# =============================================================================== apps + startup


class AppsPage(Page):
    title = "Aplikasi"
    blurb = "Tutup aplikasi berat sebelum main dan rapikan startup Windows."

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, app)
        self._attempts = 0
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", pady=(0, T.px(8)))
        Btn(top, "Segarkan", self.refresh, style="ghost").pack(side="right")
        AutoLabel(top, text="Hanya aplikasi milikmu yang tampil. Proses sistem Windows tidak pernah muncul di sini.",
                  font="ix9.small", fg=T.MUTED, bg=T.BG).pack(side="left", fill="x", expand=True)
        columns = tk.Frame(self, bg=T.BG)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1, uniform="cols")
        columns.columnconfigure(1, weight=1, uniform="cols")
        columns.rowconfigure(0, weight=1)
        self.apps = self._column(columns, 0, "Aplikasi berjalan, terbesar dulu")
        self.startup = self._column(columns, 1, "Aplikasi startup Windows")

    def _column(self, parent: tk.Misc, column: int, title: str) -> ScrollFrame:
        panel = Panel(parent)
        panel.grid(row=0, column=column, sticky="nsew",
                   padx=(0 if column == 0 else T.px(6), 0 if column == 1 else T.px(6)))
        tk.Label(panel, text=title, font="ix9.h2", fg=T.CREAM, bg=T.PANEL).pack(anchor="w", padx=T.px(14), pady=(T.px(12), T.px(8)))
        scroll = ScrollFrame(panel)
        scroll.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        return scroll

    def on_show(self) -> None:
        self._attempts = 0
        self._refresh_when_free()

    def _refresh_when_free(self) -> None:
        """Load the lists; if another job is still running (e.g. the first status read), try again shortly."""
        if not self.winfo_exists():
            return
        if not self.refresh(quiet=True) and self._attempts < 12:
            self._attempts += 1
            self.after(300, self._refresh_when_free)

    def refresh(self, quiet: bool = False) -> bool:
        def job():
            return processes.list_user_apps(), startup.list_items()

        return self.app.run_task("segarkan daftar", job, self._fill, quiet=quiet)

    def _fill(self, result) -> None:
        if not result:
            return
        apps, items = result
        self.apps.clear()
        if not apps:
            tk.Label(self.apps.inner, text="Tidak ada aplikasi yang bisa ditampilkan.", font="ix9.body", fg=T.MUTED, bg=T.PANEL).pack(padx=T.px(14), pady=T.px(14), anchor="w")
        for row in apps:
            self._app_row(row)
        self.startup.clear()
        if not items:
            tk.Label(self.startup.inner, text="Tidak ada aplikasi startup yang bisa ditampilkan.", font="ix9.body", fg=T.MUTED, bg=T.PANEL).pack(padx=T.px(14), pady=T.px(14), anchor="w")
        for item in items:
            self._startup_row(item)

    def _app_row(self, row: processes.AppRow) -> None:
        inner = self.apps.inner
        frame = tk.Frame(inner, bg=T.PANEL)
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        text = tk.Frame(frame, bg=T.PANEL)
        text.grid(row=0, column=0, sticky="ew", padx=T.px(14), pady=T.px(8))
        tk.Label(text, text=row.name, font="ix9.bodyb", fg=T.CREAM, bg=T.PANEL, anchor="w").pack(fill="x")
        tk.Label(text, text=f"{len(row.pids)} proses, {cleaner.format_size(row.rss)}", font="ix9.small", fg=T.MUTED, bg=T.PANEL, anchor="w").pack(fill="x")
        buttons = tk.Frame(frame, bg=T.PANEL)
        buttons.grid(row=0, column=1, padx=(0, T.px(12)))
        Btn(buttons, "Normalkan" if row.high else "Prioritas", lambda r=row: self._priority(r), style="ghost").pack(side="left")
        Btn(buttons, "Tutup", lambda r=row: self._close(r), style="outline").pack(side="left", padx=(T.px(6), 0))
        tk.Frame(inner, bg=T.LINE, height=1).pack(fill="x")

    def _close(self, row: processes.AppRow) -> None:
        if not self.app.confirm("Tutup aplikasi", f"Tutup {row.name} ({len(row.pids)} proses)?\n\nPekerjaan yang belum disimpan di aplikasi itu akan hilang."):
            return

        def job():
            closed = processes.close_app(list(row.pids))
            self.app.log(f"{row.name}: {closed} proses ditutup", "ok" if closed else "warn")
            return processes.list_user_apps(), startup.list_items()

        self.app.run_task(f"tutup {row.name}", job, self._fill)

    def _priority(self, row: processes.AppRow) -> None:
        make_high = not row.high

        def job():
            changed = processes.set_priority(list(row.pids), make_high)
            state = "Prioritas tinggi" if make_high else "Prioritas normal"
            self.app.log(f"{row.name}: {state} untuk {changed} proses (kembali normal kalau aplikasinya ditutup)", "ok" if changed else "warn")
            return processes.list_user_apps(), startup.list_items()

        self.app.run_task(f"prioritas {row.name}", job, self._fill)

    def _startup_row(self, item: startup.StartupItem) -> None:
        inner = self.startup.inner
        frame = tk.Frame(inner, bg=T.PANEL)
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        text = tk.Frame(frame, bg=T.PANEL)
        text.grid(row=0, column=0, sticky="ew", padx=T.px(14), pady=T.px(8))
        tk.Label(text, text=item.name, font="ix9.bodyb", fg=T.CREAM, bg=T.PANEL, anchor="w").pack(fill="x")
        tk.Label(text, text=item.source, font="ix9.small", fg=T.MUTED, bg=T.PANEL, anchor="w").pack(fill="x")
        switch = Switch(frame, command=lambda want, it=item: self._toggle_startup(it, want))
        switch.set(item.enabled)
        switch.grid(row=0, column=1, padx=T.px(14))
        tk.Frame(inner, bg=T.LINE, height=1).pack(fill="x")

    def _toggle_startup(self, item: startup.StartupItem, want: bool) -> bool:
        def job():
            ok = startup.set_enabled(item, want)
            self.app.log(f"Startup {item.name}: {'dinyalakan' if want else 'dimatikan'}" if ok else f"Startup {item.name}: gagal diubah",
                         "ok" if ok else "err")
            return ok

        return self.app.run_task(f"startup {item.name}", job, lambda ok: None if ok else self.refresh(quiet=True))


# =============================================================================== safety


class SafetyPage(Page):
    title = "Keamanan"
    blurb = "Apa yang dilakukan Marshall IX9, dan apa yang tidak pernah dilakukannya."

    POINTS = (
        ("Tanpa internet", "Kodenya tidak memakai modul jaringan apa pun. Ada tes otomatis yang gagal kalau ada yang menambahkannya."),
        ("Semua tercatat", "Setiap perubahan muncul di catatan aktivitas, dan nilai asli disimpan ke backup.json sebelum diubah."),
        ("Bisa dikembalikan", "Tiap tweak punya switch. 'Kembalikan semua' memulihkan nilai awal, bahkan setelah komputer di-restart."),
        ("Cakupan sempit", "Hanya kunci registry dan pengaturan daya yang tertulis di catatan aktivitas, folder Temp, dan aplikasi yang kamu klik sendiri."),
        ("Tanpa fitur palsu", "Tidak ada 'RAM cleaner' atau 'GPU overclock'. Tombol seperti itu tidak membantu, kadang malah memperlambat."),
    )

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, app)
        panel = Panel(self)
        panel.pack(fill="x")
        for index, (head, text) in enumerate(self.POINTS):
            if index:
                tk.Frame(panel, bg=T.LINE, height=1).pack(fill="x")
            row = tk.Frame(panel, bg=T.PANEL)
            row.pack(fill="x", padx=T.px(18), pady=T.px(11))
            tk.Label(row, text=head, font="ix9.h2", fg=T.BRASS, bg=T.PANEL, anchor="w").pack(fill="x")
            AutoLabel(row, text=text, font="ix9.body", fg=T.MUTED, bg=T.PANEL).pack(fill="x", pady=(T.px(2), 0))

        tools = tk.Frame(self, bg=T.BG)
        tools.pack(fill="x", pady=(T.px(14), 0))
        Btn(tools, "Buat restore point", app.make_restore_point, style="outline").pack(side="left")
        Btn(tools, "Buka folder backup", lambda: app.open_target(wu.data_dir()), style="ghost").pack(side="left", padx=(T.px(8), 0))
        Btn(tools, "Pengaturan daya Windows", lambda: app.open_target("ms-settings:powersleep"), style="ghost").pack(side="left", padx=(T.px(8), 0))
        Btn(tools, "Bersihkan cache DNS", app.flush_dns, style="ghost").pack(side="left", padx=(T.px(8), 0))
        self.where = tk.Label(self, text="", font="ix9.small", fg=T.MUTED, bg=T.BG, anchor="w")
        self.where.pack(fill="x", pady=(T.px(12), 0))

    def on_show(self) -> None:
        self.where.configure(text=f"Backup nilai asli: {wu.data_dir()}")
