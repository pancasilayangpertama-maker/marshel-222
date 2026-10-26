"""Windows power helpers (powercfg). Everything named get/query/on_ac is read-only."""
from __future__ import annotations

import ctypes
import re
from typing import Optional

from . import winutil as wu

GUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
HEX_RE = re.compile(r"0x[0-9a-fA-F]+")

# Power plans / "power mode" overlays
SCHEME_HIGH = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
SCHEME_ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
OVERLAY_MAX = "ded574b5-45a0-4f42-8737-46345c09c238"  # "Best performance"
OVERLAY_NONE = "00000000-0000-0000-0000-000000000000"
_OVERLAY_ALIAS = {OVERLAY_MAX: "OVERLAY_SCHEME_MAX", OVERLAY_NONE: "OVERLAY_SCHEME_NONE"}

# Sub-groups and settings (documented power-setting GUIDs)
SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
SUB_USB = "2a737441-1930-4402-8d77-b2bebba308a3"
SUB_PCIE = "501a4d13-42af-4429-9fd1-a8218c268e20"
SUB_WIRELESS = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1"

PERFBOOSTMODE = "be337238-0d82-4146-a960-4f3749d470c7"
PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"
PERFEPP = "36687f9e-e3a5-4dbf-b1dc-15eb381c6863"
SYSCOOLPOL = "94d3a615-a899-4ac5-ae2b-e4d8f634367f"
USB_SELECTIVE_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
PCIE_ASPM = "ee12f906-d277-404b-b6da-e5fa1a576df5"
WIFI_POWER_SAVING = "12bbebe6-58d6-4636-95bb-3217ef867c1a"

_OVERLAY_KEY = r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes"


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_uint32),
        ("BatteryFullLifeTime", ctypes.c_uint32),
    ]


def on_ac() -> Optional[bool]:
    """True = charger connected, False = on battery, None = unknown (e.g. desktop)."""
    if not wu.IS_WIN:
        return None
    try:
        status = _PowerStatus()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        if status.ACLineStatus == 1:
            return True
        if status.ACLineStatus == 0:
            return False
    except Exception:
        pass
    return None


def active_scheme() -> Optional[str]:
    code, out = wu.run(["powercfg", "/getactivescheme"], timeout=15)
    if code != 0:
        return None
    found = GUID_RE.search(out)
    return found.group(0).lower() if found else None


def set_active(scheme: str) -> bool:
    code, _ = wu.run(["powercfg", "/setactive", scheme], timeout=15)
    return code == 0


def query_ac(scheme: str, sub: str, setting: str) -> Optional[int]:
    """Current 'plugged in' value of one setting, or None when unsupported on this PC."""
    code, out = wu.run(["powercfg", "/query", scheme, sub, setting], timeout=15)
    if code != 0:
        return None
    values = HEX_RE.findall(out)
    if len(values) < 2:
        return None
    try:
        return int(values[-2], 16)  # the last two numbers are always: AC index, DC index
    except ValueError:
        return None


def set_ac(scheme: str, sub: str, setting: str, value: int) -> bool:
    code, _ = wu.run(["powercfg", "/setacvalueindex", scheme, sub, setting, str(int(value))], timeout=15)
    return code == 0


def overlay_get() -> str:
    rec = wu.reg_read("HKLM", _OVERLAY_KEY, "ActiveOverlayAcPowerScheme")
    if rec and isinstance(rec[0], str):
        found = GUID_RE.search(rec[0])
        if found:
            return found.group(0).lower()
    return OVERLAY_NONE


def overlay_set(guid: str) -> bool:
    guid = (guid or OVERLAY_NONE).lower()
    alias = _OVERLAY_ALIAS.get(guid)
    if alias:
        code, _ = wu.run(["powercfg", "/overlaysetactive", alias], timeout=15)
        if code == 0:
            return True
    code, _ = wu.run(["powercfg", "/overlaysetactive", guid], timeout=15)
    return code == 0
