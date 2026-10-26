"""Startup apps: list them and switch them on/off.

Same mechanism Task Manager uses: a flag under ...\\Explorer\\StartupApproved. The entry itself
(the Run key value or the shortcut) is never deleted, so switching back on restores it exactly.
"""
from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass
from typing import List, Tuple

from . import winutil as wu

_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
_RUN_SOURCES: Tuple[Tuple[str, str, str, str], ...] = (
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run", "Run", "Pengguna"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run", "Run", "Semua pengguna"),
    ("HKLM", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Run32", "Semua pengguna (32-bit)"),
)
_HIDDEN_WORDS = ("securityhealth", "windows security", "defender")  # never offered


@dataclass
class StartupItem:
    name: str
    command: str
    source: str
    approved_key: str
    enabled: bool


def _hidden(name: str) -> bool:
    low = name.lower()
    return any(word in low for word in _HIDDEN_WORDS)


def _is_enabled(approved_key: str, name: str) -> bool:
    rec = wu.reg_read("HKCU", approved_key, name)
    if rec and isinstance(rec[0], (bytes, bytearray)) and len(rec[0]) >= 1:
        return (rec[0][0] & 1) == 0  # even first byte = enabled, odd = disabled
    return True


def _startup_folders() -> List[Tuple[str, str]]:
    folders: List[Tuple[str, str]] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        folders.append((os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"), "Folder Startup pengguna"))
    programdata = os.environ.get("ProgramData")
    if programdata:
        folders.append((os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs", "StartUp"), "Folder Startup semua pengguna"))
    return folders


def list_items() -> List[StartupItem]:
    items: List[StartupItem] = []
    for hive, path, sub, label in _RUN_SOURCES:
        approved = f"{_APPROVED}\\{sub}"
        for name, value, _typ in wu.reg_values(hive, path):
            if name and not _hidden(name):
                items.append(StartupItem(name, str(value), label, approved, _is_enabled(approved, name)))
    approved = f"{_APPROVED}\\StartupFolder"
    for folder, label in _startup_folders():
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for filename in names:
            if filename.lower() == "desktop.ini" or _hidden(filename):
                continue
            items.append(StartupItem(filename, os.path.join(folder, filename), label, approved, _is_enabled(approved, filename)))
    return items


def _flag(enabled: bool) -> bytes:
    if enabled:
        return struct.pack("<I", 2) + bytes(8)
    filetime = int((time.time() + 11644473600) * 10_000_000)  # Unix epoch -> Windows FILETIME
    return struct.pack("<I", 3) + struct.pack("<Q", filetime)


def set_enabled(item: StartupItem, enabled: bool) -> bool:
    try:
        wu.reg_write("HKCU", item.approved_key, item.name, _flag(enabled), wu.REG_BINARY)
        item.enabled = enabled
        return True
    except OSError:
        return False
