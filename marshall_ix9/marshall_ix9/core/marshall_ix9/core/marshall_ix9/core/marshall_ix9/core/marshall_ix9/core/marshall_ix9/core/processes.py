"""List, close or prioritise the user's OWN background apps. System processes are never listed."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

# Belt and braces: anything running from the Windows folder or under another account is skipped
# anyway, these names are additionally never offered.
PROTECTED = frozenset({
    "system", "system idle process", "registry", "memory compression",
    "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "winlogon.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "sihost.exe", "taskhostw.exe", "ctfmon.exe", "searchhost.exe", "searchapp.exe",
    "searchindexer.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "textinputhost.exe", "runtimebroker.exe", "applicationframehost.exe", "audiodg.exe",
    "conhost.exe", "dllhost.exe", "wudfhost.exe", "spoolsv.exe", "backgroundtaskhost.exe",
    "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe", "securityhealthsystray.exe",
    "msedgewebview2.exe", "taskmgr.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "python.exe", "pythonw.exe", "marshallix9.exe",
})


@dataclass
class AppRow:
    name: str
    pids: List[int]
    rss: int
    high: bool = False


def list_user_apps(limit: int = 14) -> List[AppRow]:
    """The user's own apps grouped by name, biggest memory use first."""
    if psutil is None:
        return []
    try:
        me = psutil.Process().username()
    except Exception:
        me = None
    windir = (os.environ.get("SystemRoot") or r"C:\Windows").lower()
    own_pid = os.getpid()
    groups: Dict[str, AppRow] = {}
    for proc in psutil.process_iter(["pid", "name", "username", "memory_info", "exe"]):
        info = proc.info
        name = info.get("name") or ""
        low = name.lower()
        if not name or low in PROTECTED or info.get("pid") == own_pid:
            continue
        if me is not None and info.get("username") != me:
            continue
        exe = info.get("exe") or ""
        if not exe or exe.lower().startswith(windir):
            continue
        mem = info.get("memory_info")
        row = groups.get(low)
        if row is None:
            row = groups[low] = AppRow(name, [], 0)
        row.pids.append(info["pid"])
        row.rss += mem.rss if mem else 0
    rows = sorted(groups.values(), key=lambda r: r.rss, reverse=True)[:limit]
    for row in rows:
        try:
            row.high = psutil.Process(row.pids[0]).nice() == psutil.HIGH_PRIORITY_CLASS
        except Exception:
            row.high = False
    return rows


def close_app(pids: List[int]) -> int:
    """Ask each process to terminate, force-kill what is still alive after 3 seconds."""
    if psutil is None:
        return 0
    procs = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _gone, alive = psutil.wait_procs(procs, timeout=3)
    for proc in alive:
        try:
            proc.kill()
        except Exception:
            pass
    return len(procs)


def set_priority(pids: List[int], high: bool) -> int:
    """Switch between High and Normal priority. Realtime is never used."""
    if psutil is None:
        return 0
    try:
        wanted = psutil.HIGH_PRIORITY_CLASS if high else psutil.NORMAL_PRIORITY_CLASS
    except AttributeError:  # not Windows
        return 0
    changed = 0
    for pid in pids:
        try:
            psutil.Process(pid).nice(wanted)
            changed += 1
        except Exception:
            continue
    return changed
