"""Read-only device information. Registry reads only; no WMI, no PowerShell, no network."""
from __future__ import annotations

import os
import platform
import sys
from typing import List, Tuple

from . import winutil as wu

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

_GPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11cd-bfc1-08002be10318}"


def _text(hive: str, path: str, name: str) -> str:
    rec = wu.reg_read(hive, path, name)
    return " ".join(str(rec[0]).split()) if rec and rec[0] else ""


def device_model() -> str:
    key = r"HARDWARE\DESCRIPTION\System\BIOS"
    parts = [_text("HKLM", key, "SystemManufacturer"), _text("HKLM", key, "SystemProductName")]
    return " ".join(p for p in parts if p) or "tidak terbaca"


def cpu_name() -> str:
    name = _text("HKLM", r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
    return name or platform.processor() or "tidak terbaca"


def gpu_names() -> List[str]:
    names: List[str] = []
    for sub in wu.reg_subkeys("HKLM", _GPU_CLASS):
        if len(sub) == 4 and sub.isdigit():
            name = _text("HKLM", f"{_GPU_CLASS}\\{sub}", "DriverDesc")
            if name and "basic" not in name.lower() and name not in names:
                names.append(name)
    return names


def os_name() -> str:
    if not wu.IS_WIN:
        return platform.system() or "tidak terbaca"
    try:
        build = sys.getwindowsversion().build  # type: ignore[attr-defined]
    except Exception:
        build = 0
    base = "Windows 11" if build >= 22000 else "Windows 10"
    version = _text("HKLM", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "DisplayVersion")
    return f"{base} {version}".strip() + (f" (build {build})" if build else "")


def system_drive() -> str:
    return (os.environ.get("SystemDrive") or "C:") + "\\"


def collect() -> List[Tuple[str, str]]:
    """Label/value pairs for the dashboard."""
    ram = f"{psutil.virtual_memory().total / 1024 ** 3:.1f} GB" if psutil else "tidak terbaca"
    gpus = gpu_names()
    return [
        ("Perangkat", device_model()),
        ("Prosesor", cpu_name()),
        ("Grafis", ", ".join(gpus) if gpus else "tidak terbaca"),
        ("Memori", ram),
        ("Sistem", os_name()),
    ]
