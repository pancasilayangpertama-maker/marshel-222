"""Low-level helpers shared by every module.

Admin check, running external commands, registry access and the backup store.
Nothing in this package opens a network connection.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import winreg
else:  # lets the package import (and be unit-tested) on Linux / macOS
    winreg = None  # type: ignore[assignment]

REG_SZ = 1
REG_EXPAND_SZ = 2
REG_BINARY = 3
REG_DWORD = 4

_CREATE_NO_WINDOW = 0x08000000


def is_admin() -> bool:
    if not IS_WIN:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run(cmd: List[str], timeout: int = 60) -> Tuple[int, str]:
    """Run an external command without opening a console window."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW if IS_WIN else 0,
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError:
        return 127, "command not found"
    except Exception as exc:  # pragma: no cover - defensive
        return 1, str(exc)


def data_dir() -> str:
    """Folder for backup.json and error.log (%APPDATA%\\MarshallIX9)."""
    appdata = os.environ.get("APPDATA")
    path = os.path.join(appdata, "MarshallIX9") if appdata else os.path.join(os.path.expanduser("~"), ".marshall_ix9")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------- backup


def encode_value(value: Any) -> Any:
    """Make a registry value JSON-safe (bytes -> {'bin': hex})."""
    if isinstance(value, (bytes, bytearray)):
        return {"bin": bytes(value).hex()}
    return value


def decode_value(value: Any) -> Any:
    if isinstance(value, dict) and "bin" in value:
        return bytes.fromhex(value["bin"])
    return value


class BackupStore:
    """JSON file holding the ORIGINAL values, written before anything is changed."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.path.join(data_dir(), "backup.json")
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._data = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._data = {}

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data.get(key)

    def put_if_absent(self, key: str, record: Dict[str, Any]) -> bool:
        with self._lock:
            if key in self._data:
                return False
            self._data[key] = record
            return True

    def pop(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self, prefix: str = "") -> List[str]:
        with self._lock:
            return [k for k in self._data if k.startswith(prefix)]


# --------------------------------------------------------------------------- registry


def _hive(name: str):
    return winreg.HKEY_CURRENT_USER if name == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def reg_read(hive: str, path: str, name: str) -> Optional[Tuple[Any, int]]:
    """Return (value, type) or None when the key/value does not exist."""
    if not IS_WIN:
        return None
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return winreg.QueryValueEx(key, name)
    except OSError:
        return None


def reg_write(hive: str, path: str, name: str, value: Any, typ: int) -> None:
    if not IS_WIN:
        raise OSError("Hanya untuk Windows")
    with winreg.CreateKeyEx(_hive(hive), path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, name, 0, typ, value)


def reg_delete(hive: str, path: str, name: str) -> None:
    if not IS_WIN:
        return
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass


def reg_values(hive: str, path: str) -> List[Tuple[str, Any, int]]:
    """All (name, value, type) under a key; empty list when the key is missing."""
    found: List[Tuple[str, Any, int]] = []
    if not IS_WIN:
        return found
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            index = 0
            while True:
                try:
                    found.append(winreg.EnumValue(key, index))
                except OSError:
                    break
                index += 1
    except OSError:
        pass
    return found


def reg_subkeys(hive: str, path: str) -> List[str]:
    found: List[str] = []
    if not IS_WIN:
        return found
    try:
        with winreg.OpenKey(_hive(hive), path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            index = 0
            while True:
                try:
                    found.append(winreg.EnumKey(key, index))
                except OSError:
                    break
                index += 1
    except OSError:
        pass
    return found


# --------------------------------------------------------------------------- small Win32 helpers


def broadcast_setting_change(param: str = "ImmersiveColorSet") -> None:
    """Tell Windows a user setting changed so it re-reads it right away."""
    if not IS_WIN:
        return
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        fn = user32.SendMessageTimeoutW
        fn.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_wchar_p,
            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
        ]
        fn.restype = ctypes.c_ssize_t
        result = ctypes.c_size_t()
        fn(0xFFFF, 0x001A, 0, param, 0x0002, 1500, ctypes.byref(result))  # HWND_BROADCAST, WM_SETTINGCHANGE
    except Exception:
        pass


def apply_mouse_settings_now() -> None:
    """Re-read the pointer-precision values from the registry and apply them instantly."""
    if not IS_WIN:
        return

    def number(name: str, default: int) -> int:
        rec = reg_read("HKCU", r"Control Panel\Mouse", name)
        try:
            return int(rec[0]) if rec else default
        except (TypeError, ValueError):
            return default

    try:
        values = (ctypes.c_int * 3)(number("MouseThreshold1", 6), number("MouseThreshold2", 10), number("MouseSpeed", 1))
        ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, values, 0x03)  # SPI_SETMOUSE, update+broadcast
    except Exception:
        pass
