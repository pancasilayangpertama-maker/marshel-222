"""Every system change Marshall IX9 can make, written as plain data plus tiny classes.

Rules every tweak follows:
  * the ORIGINAL value is written to backup.json before the first change,
  * undo() puts back exactly that value (or deletes the value if it did not exist),
  * nothing here talks to the network.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from . import power
from . import winutil as wu
from .winutil import REG_DWORD, REG_SZ, BackupStore

Log = Callable[..., None]  # log(message, level="info")

NO_DEFAULT = object()


@dataclass(frozen=True)
class RegSet:
    hive: str
    path: str
    name: str
    value: object
    typ: int = REG_DWORD
    default: object = NO_DEFAULT  # the Windows default (None = normally absent); used if no backup exists

    def key(self) -> str:
        return f"reg|{self.hive}|{self.path}|{self.name}"


class Tweak:
    id = ""
    title = ""
    desc = ""
    note = ""            # extra hint under the description
    impact = 1           # 1 = small, 2 = noticeable, 3 = biggest lever
    admin = False
    ac_only = False      # only has an effect while the charger is connected
    reboot = False
    recommended = True   # part of the one-click Boost

    def __init__(self, backup: BackupStore) -> None:
        self.bk = backup

    def status(self) -> Optional[bool]:
        raise NotImplementedError

    def apply(self, log: Log) -> bool:
        raise NotImplementedError

    def undo(self, log: Log) -> bool:
        raise NotImplementedError

    def has_backup(self) -> bool:
        raise NotImplementedError

    def _preflight(self, log: Log, need_ac: bool = False) -> bool:
        if not wu.IS_WIN:
            log(f"{self.title}: hanya bisa dijalankan di Windows", "warn")
            return False
        if self.admin and not wu.is_admin():
            log(f"{self.title}: perlu Administrator (jalankan sebagai admin)", "warn")
            return False
        if need_ac and power.on_ac() is False:
            log(f"{self.title}: colokkan charger dulu, bagian ini hanya untuk mode dicas", "warn")
            return False
        return True


# --------------------------------------------------------------------------- registry tweaks


class RegistryTweak(Tweak):
    values: Tuple[RegSet, ...] = ()

    def after_change(self) -> None:
        """Hook: make Windows notice the change right away."""

    def status(self) -> Optional[bool]:
        if not wu.IS_WIN:
            return None
        for v in self.values:
            cur = wu.reg_read(v.hive, v.path, v.name)
            if cur is None or cur[0] != v.value:
                return False
        return True

    def has_backup(self) -> bool:
        return any(self.bk.get(v.key()) is not None for v in self.values)

    def apply(self, log: Log) -> bool:
        if not self._preflight(log):
            return False
        ok = True
        for v in self.values:
            try:
                if self.bk.get(v.key()) is None:
                    cur = wu.reg_read(v.hive, v.path, v.name)
                    self.bk.put_if_absent(v.key(), {
                        "existed": cur is not None,
                        "type": cur[1] if cur else None,
                        "value": wu.encode_value(cur[0]) if cur else None,
                    })
                    self.bk.save()  # the backup reaches the disk BEFORE the change
                wu.reg_write(v.hive, v.path, v.name, v.value, v.typ)
                log(f"  {v.hive}\\{v.path}\\{v.name} = {v.value!r}", "dim")
            except OSError as exc:
                ok = False
                log(f"  gagal menulis {v.name}: {exc}", "err")
        self.after_change()
        log(f"{self.title}: {'aktif' if ok else 'selesai dengan error'}", "ok" if ok else "warn")
        return ok

    def undo(self, log: Log) -> bool:
        if not self._preflight(log):
            return False
        ok = True
        touched = False
        for v in self.values:
            rec = self.bk.get(v.key())
            try:
                if rec is not None:
                    if rec.get("existed"):
                        wu.reg_write(v.hive, v.path, v.name, wu.decode_value(rec.get("value")), rec["type"])
                    else:
                        wu.reg_delete(v.hive, v.path, v.name)
                    self.bk.pop(v.key())
                    touched = True
                elif v.default is not NO_DEFAULT:
                    # no backup (e.g. changed by hand earlier): fall back to the Windows default
                    cur = wu.reg_read(v.hive, v.path, v.name)
                    if cur is not None and cur[0] == v.value:
                        if v.default is None:
                            wu.reg_delete(v.hive, v.path, v.name)
                        else:
                            wu.reg_write(v.hive, v.path, v.name, v.default, v.typ)
                        touched = True
            except OSError as exc:
                ok = False
                log(f"  gagal memulihkan {v.name}: {exc}", "err")
        self.bk.save()
        self.after_change()
        if touched:
            log(f"{self.title}: dikembalikan ke nilai awal", "ok" if ok else "warn")
        else:
            log(f"{self.title}: tidak ada yang perlu dikembalikan", "dim")
        return ok


class GameMode(RegistryTweak):
    id = "game_mode"
    title = "Game Mode aktif"
    desc = ("Windows memprioritaskan game yang sedang dimainkan dan menahan update driver / Windows Update "
            "agar tidak mengganggu di tengah game.")
    impact = 1
    values = (
        RegSet("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1, REG_DWORD, None),
        RegSet("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1, REG_DWORD, None),
    )


class GameDvr(RegistryTweak):
    id = "game_dvr"
    title = "Matikan perekaman latar Game Bar"
    desc = ("Xbox Game Bar berhenti merekam di latar belakang, jadi CPU, GPU, dan disk sedikit lebih lega. "
            "Rekam / clip lewat Game Bar tidak akan jalan selama ini aktif.")
    impact = 1
    values = (
        RegSet("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", 0, REG_DWORD, 1),
        RegSet("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0, REG_DWORD, 1),
    )


class Transparency(RegistryTweak):
    id = "transparency"
    title = "Matikan efek transparan"
    desc = ("Efek blur / transparan di Start, taskbar, dan jendela dimatikan. iGPU berbagi memori dengan CPU, "
            "jadi beban grafis harian ikut turun.")
    impact = 2
    values = (
        RegSet("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0, REG_DWORD, 1),
    )

    def after_change(self) -> None:
        wu.broadcast_setting_change("ImmersiveColorSet")


class Mmcss(RegistryTweak):
    id = "mmcss"
    title = "Prioritas scheduler untuk game (MMCSS)"
    desc = ("Naikkan prioritas tugas 'Games' dan matikan throttling jaringan multimedia. "
            "Efeknya kecil, tapi aman dan bisa dikembalikan.")
    impact = 1
    admin = True
    reboot = True
    _profile = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
    values = (
        RegSet("HKLM", _profile, "NetworkThrottlingIndex", 0xFFFFFFFF, REG_DWORD, 10),
        RegSet("HKLM", _profile, "SystemResponsiveness", 0, REG_DWORD, 20),
        RegSet("HKLM", _profile + r"\Tasks\Games", "Priority", 6, REG_DWORD, 2),
        RegSet("HKLM", _profile + r"\Tasks\Games", "Scheduling Category", "High", REG_SZ, "Medium"),
        RegSet("HKLM", _profile + r"\Tasks\Games", "SFIO Priority", "High", REG_SZ, "Normal"),
    )


class PointerPrecision(RegistryTweak):
    id = "pointer"
    title = "Pointer precision mati"
    desc = ("Matikan 'Enhance pointer precision' (akselerasi mouse) supaya gerakan mouse konsisten saat aim. "
            "Ini soal selera, jadi tidak ikut Boost.")
    impact = 1
    recommended = False
    values = (
        RegSet("HKCU", r"Control Panel\Mouse", "MouseSpeed", "0", REG_SZ, "1"),
        RegSet("HKCU", r"Control Panel\Mouse", "MouseThreshold1", "0", REG_SZ, "6"),
        RegSet("HKCU", r"Control Panel\Mouse", "MouseThreshold2", "0", REG_SZ, "10"),
    )

    def after_change(self) -> None:
        wu.apply_mouse_settings_now()


# --------------------------------------------------------------------------- power tweaks


class PowerModeTweak(Tweak):
    id = "power_mode"
    title = "Mode daya: Best performance"
    desc = ("Saat charger tersambung, Windows memakai mode Best performance: CPU dan iGPU naik clock lebih "
            "agresif dan lebih lama. Mode baterai tidak diubah.")
    impact = 3
    admin = True
    ac_only = True
    _KEY = "power|power_mode"

    def status(self) -> Optional[bool]:
        if not wu.IS_WIN:
            return None
        if power.overlay_get() == power.OVERLAY_MAX:
            return True
        return power.active_scheme() in (power.SCHEME_HIGH, power.SCHEME_ULTIMATE)

    def has_backup(self) -> bool:
        return self.bk.get(self._KEY) is not None

    def apply(self, log: Log) -> bool:
        if not self._preflight(log, need_ac=True):
            return False
        if self.bk.get(self._KEY) is None:
            self.bk.put_if_absent(self._KEY, {"overlay": power.overlay_get(), "scheme": power.active_scheme()})
            self.bk.save()
        if power.overlay_set(power.OVERLAY_MAX):
            log(f"{self.title}: aktif", "ok")
            return True
        log("  mode 'Best performance' tidak tersedia, memakai rencana daya High performance", "warn")
        if power.set_active(power.SCHEME_HIGH):
            log(f"{self.title}: aktif (High performance)", "ok")
            return True
        log(f"{self.title}: gagal diterapkan", "err")
        return False

    def undo(self, log: Log) -> bool:
        if not self._preflight(log, need_ac=True):
            return False
        rec = self.bk.get(self._KEY)
        if rec is None:
            if self.status():
                ok = power.overlay_set(power.OVERLAY_NONE)
                log(f"{self.title}: dikembalikan ke mode default Windows", "ok" if ok else "warn")
                return ok
            log(f"{self.title}: tidak ada yang perlu dikembalikan", "dim")
            return True
        overlay_ok = power.overlay_set(rec.get("overlay") or power.OVERLAY_NONE)
        scheme_ok = True
        scheme = rec.get("scheme")
        if scheme and power.active_scheme() != scheme:
            scheme_ok = power.set_active(scheme)
        self.bk.pop(self._KEY)
        self.bk.save()
        ok = overlay_ok or scheme_ok
        log(f"{self.title}: dikembalikan ke nilai awal", "ok" if ok else "warn")
        return ok


class PowerSettingsTweak(Tweak):
    """Changes 'plugged in' values of the ACTIVE power plan. Battery values are never touched."""

    settings: Tuple[Tuple[str, str, str, int], ...] = ()  # (label, subgroup, setting, value)
    admin = True
    ac_only = True

    def _prefix(self) -> str:
        return f"power|{self.id}|"

    def has_backup(self) -> bool:
        return bool(self.bk.keys(self._prefix()))

    def status(self) -> Optional[bool]:
        if not wu.IS_WIN:
            return None
        scheme = power.active_scheme()
        if not scheme:
            return None
        checked = 0
        for _label, sub, setting, value in self.settings:
            current = power.query_ac(scheme, sub, setting)
            if current is None:
                continue
            checked += 1
            if current != value:
                return False
        return True if checked else None

    def apply(self, log: Log) -> bool:
        if not self._preflight(log):
            return False
        scheme = power.active_scheme()
        if not scheme:
            log(f"{self.title}: rencana daya aktif tidak terbaca", "err")
            return False
        applied = 0
        for label, sub, setting, value in self.settings:
            current = power.query_ac(scheme, sub, setting)
            if current is None:
                log(f"  {label}: tidak didukung di PC ini, dilewati", "dim")
                continue
            key = f"{self._prefix()}{scheme}|{setting}"
            if self.bk.get(key) is None:
                self.bk.put_if_absent(key, {"scheme": scheme, "sub": sub, "setting": setting, "ac": current})
                self.bk.save()
            if power.set_ac(scheme, sub, setting, value):
                applied += 1
                log(f"  {label}", "dim")
            else:
                log(f"  {label}: gagal diterapkan", "warn")
        power.set_active(scheme)  # re-activate so Windows applies the new values now
        log(f"{self.title}: {'aktif' if applied else 'tidak ada yang bisa diterapkan'}", "ok" if applied else "warn")
        return applied > 0

    def undo(self, log: Log) -> bool:
        if not self._preflight(log):
            return False
        keys = self.bk.keys(self._prefix())
        if not keys:
            log(f"{self.title}: tidak ada yang perlu dikembalikan", "dim")
            return True
        ok = True
        for key in keys:
            rec = self.bk.get(key) or {}
            try:
                if power.set_ac(rec["scheme"], rec["sub"], rec["setting"], int(rec["ac"])):
                    self.bk.pop(key)
                else:
                    ok = False
            except (KeyError, TypeError, ValueError):
                self.bk.pop(key)
        self.bk.save()
        current = power.active_scheme()
        if current:
            power.set_active(current)
        log(f"{self.title}: dikembalikan ke nilai awal", "ok" if ok else "warn")
        return ok


class CpuCooling(PowerSettingsTweak):
    id = "cpu_cooling"
    title = "CPU boost agresif + kipas lebih dulu"
    desc = ("CPU boleh boost penuh dan kipas menyala lebih awal sebelum clock diturunkan. "
            "Cocok untuk laptop tipis dengan cooling pad.")
    impact = 3
    settings = (
        ("Processor boost mode: Aggressive", power.SUB_PROCESSOR, power.PERFBOOSTMODE, 2),
        ("Maximum processor state: 100%", power.SUB_PROCESSOR, power.PROCTHROTTLEMAX, 100),
        ("Energy preference: Performance", power.SUB_PROCESSOR, power.PERFEPP, 0),
        ("Cooling policy: Active", power.SUB_PROCESSOR, power.SYSCOOLPOL, 1),
    )


class DevicePower(PowerSettingsTweak):
    id = "device_power"
    title = "Tanpa hemat daya USB, PCIe, dan Wi-Fi"
    desc = ("Penghematan daya USB, PCIe, dan Wi-Fi dimatikan saat dicas. Mouse lebih responsif dan "
            "ping Wi-Fi lebih stabil.")
    impact = 2
    settings = (
        ("USB selective suspend: Disabled", power.SUB_USB, power.USB_SELECTIVE_SUSPEND, 0),
        ("PCI Express link state: Off", power.SUB_PCIE, power.PCIE_ASPM, 0),
        ("Wi-Fi power saving: Maximum performance", power.SUB_WIRELESS, power.WIFI_POWER_SAVING, 0),
    )


# --------------------------------------------------------------------------- bundle + helpers


def build_tweaks(backup: BackupStore) -> List[Tweak]:
    classes = (PowerModeTweak, CpuCooling, DevicePower, GameMode, GameDvr, Transparency, Mmcss, PointerPrecision)
    return [cls(backup) for cls in classes]


def safe_status(tweak: Tweak) -> Optional[bool]:
    try:
        return tweak.status()
    except Exception:
        return None


def snapshot(tweaks: List[Tweak]) -> Dict[str, Optional[bool]]:
    return {t.id: safe_status(t) for t in tweaks}


def boost(tweaks: List[Tweak], log: Log, restore_point: bool = True) -> Dict[str, bool]:
    """Apply every recommended tweak. Each one is backed up first and can be undone."""
    if restore_point:
        create_restore_point(log)
    results: Dict[str, bool] = {}
    for tweak in tweaks:
        if not tweak.recommended:
            continue
        log(f"> {tweak.title}", "info")
        try:
            results[tweak.id] = tweak.apply(log)
        except Exception as exc:  # one failing tweak must not stop the others
            results[tweak.id] = False
            log(f"{tweak.title}: error tak terduga: {exc}", "err")
    done = sum(1 for ok in results.values() if ok)
    log(f"Boost selesai: {done} dari {len(results)} tweak aktif", "ok" if done == len(results) else "warn")
    return results


def restore_all(tweaks: List[Tweak], log: Log) -> int:
    """Undo everything this app changed (only tweaks that have a backup, or are active now)."""
    restored = 0
    for tweak in tweaks:
        if tweak.has_backup() or safe_status(tweak):
            try:
                if tweak.undo(log):
                    restored += 1
            except Exception as exc:
                log(f"{tweak.title}: error saat undo: {exc}", "err")
    log(f"Pemulihan selesai ({restored} tweak diproses)", "ok")
    return restored


def create_restore_point(log: Log) -> bool:
    """Ask Windows for a System Restore point. Failure is not fatal: the app has its own backup."""
    if not wu.IS_WIN:
        return False
    if not wu.is_admin():
        log("Restore point butuh Administrator, dilewati", "warn")
        return False
    log("Membuat System Restore point (bisa 10-30 detik)...", "info")
    script = (
        "try { Checkpoint-Computer -Description 'Marshall IX9' -RestorePointType MODIFY_SETTINGS "
        "-ErrorAction Stop -WarningAction Stop; 'OK' } catch { 'ERR: ' + $_.Exception.Message }"
    )
    code, out = wu.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], timeout=180)
    lines = out.strip().splitlines()
    last = lines[-1].strip() if lines else ""
    if last == "OK":
        log("Restore point dibuat", "ok")
        return True
    if "1440" in out:
        log("Sudah ada restore point dalam 24 jam terakhir, memakai yang itu", "dim")
        return True
    log("Restore point tidak bisa dibuat (System Protection mungkin mati). Lanjut, backup bawaan tetap dipakai.", "warn")
    return False


def flush_dns(log: Log) -> bool:
    code, out = wu.run(["ipconfig", "/flushdns"], timeout=20)
    log("Cache DNS dibersihkan" if code == 0 else f"Flush DNS gagal: {out[:80]}", "ok" if code == 0 else "warn")
    return code == 0
