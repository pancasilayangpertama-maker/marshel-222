"""Disk cleaner. Only touches a short list of well-known junk folders.

Safety rules:
  * paths come from environment variables + fixed sub-folders, never from user input,
  * a folder is refused unless it really looks like a temp folder (and is never a drive root),
  * symlinks, junctions and other reparse points are never followed,
  * files younger than `min_age_days` are kept, so a running installer is not broken,
  * a file that is in use simply fails to delete and is skipped.
"""
from __future__ import annotations

import ctypes
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Tuple

from . import winutil as wu

_REPARSE_POINT = 0x400


def _env_path(var: str, *parts: str) -> Optional[str]:
    base = os.environ.get(var)
    return os.path.join(base, *parts) if base else None


def _user_temp() -> List[str]:
    return [tempfile.gettempdir()]


def _system_temp() -> List[str]:
    path = _env_path("SystemRoot", "Temp")
    return [path] if path else []


def _crash_reports() -> List[str]:
    candidates = [
        _env_path("LOCALAPPDATA", "CrashDumps"),
        _env_path("LOCALAPPDATA", "Microsoft", "Windows", "WER", "ReportArchive"),
        _env_path("LOCALAPPDATA", "Microsoft", "Windows", "WER", "ReportQueue"),
        _env_path("ProgramData", "Microsoft", "Windows", "WER", "ReportArchive"),
        _env_path("ProgramData", "Microsoft", "Windows", "WER", "ReportQueue"),
        _env_path("SystemRoot", "Minidump"),
    ]
    return [c for c in candidates if c]


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    desc: str
    min_age_days: float
    roots: Callable[[], List[str]]
    recycle: bool = False
    must_be_temp: bool = False  # extra guard for folders that come from %TEMP% / %SystemRoot%\Temp


CATEGORIES: Tuple[Category, ...] = (
    Category("user_temp", "File sementara pengguna",
             "Sisa file aplikasi di folder Temp milikmu. Hanya yang lebih tua dari 24 jam.",
             1.0, _user_temp, must_be_temp=True),
    Category("system_temp", "File sementara Windows",
             "Folder Temp milik Windows (perlu Administrator). Hanya yang lebih tua dari 24 jam.",
             1.0, _system_temp, must_be_temp=True),
    Category("crash", "Crash dump dan laporan error",
             "Dump crash dan laporan error Windows yang menumpuk.",
             0.0, _crash_reports),
    Category("recycle", "Recycle Bin",
             "Mengosongkan Recycle Bin secara permanen.",
             0.0, lambda: [], recycle=True),
)


def format_size(num: float) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover


def _root_ok(cat: Category, root: Optional[str]) -> bool:
    if not root or not os.path.isdir(root):
        return False
    norm = os.path.normpath(root)
    _drive, rest = os.path.splitdrive(norm)
    if not rest.strip("\\/"):  # a drive root such as C:\
        return False
    if cat.must_be_temp and os.path.basename(norm).lower() not in ("temp", "tmp"):
        return False
    return True


def _valid_roots(cat: Category) -> List[str]:
    return [r for r in cat.roots() if _root_ok(cat, r)]


def _is_reparse(entry: "os.DirEntry[str]") -> bool:
    try:
        if entry.is_symlink():
            return True
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & _REPARSE_POINT)
    except OSError:
        return True  # when in doubt, leave it alone


def _cutoff(cat: Category, include_recent: bool) -> Optional[float]:
    if include_recent or cat.min_age_days <= 0:
        return None
    return time.time() - cat.min_age_days * 86400


def _walk_files(root: str, cutoff: Optional[float]) -> Iterator[Tuple[str, int]]:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if _is_reparse(entry):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if cutoff is not None and info.st_mtime > cutoff:
                    continue
                yield entry.path, info.st_size


def _snapshot_dirs(root: str) -> List[Tuple[str, float]]:
    """(folder, mtime) for every real sub-folder. Taken BEFORE deleting, because deleting changes mtimes."""
    found: List[Tuple[str, float]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if _is_reparse(entry) or not entry.is_dir(follow_symlinks=False):
                        continue
                    found.append((entry.path, entry.stat(follow_symlinks=False).st_mtime))
                except OSError:
                    continue
                stack.append(entry.path)
    return found


def _prune_empty_dirs(snapshot: List[Tuple[str, float]], cutoff: Optional[float]) -> None:
    for folder, mtime in sorted(snapshot, key=lambda item: len(item[0]), reverse=True):  # children first
        if cutoff is not None and mtime > cutoff:
            continue  # a folder touched recently may belong to a running installer
        try:
            os.rmdir(folder)  # only succeeds when the folder is empty
        except OSError:
            pass


# --------------------------------------------------------------------------- recycle bin


def _recycle_query() -> Optional[Tuple[int, int]]:
    if not wu.IS_WIN:
        return None
    try:
        for pack in (1, 8):  # the header packs this struct; try both layouts to be safe
            class _Info(ctypes.Structure):
                _pack_ = pack
                _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]

            info = _Info()
            info.cbSize = ctypes.sizeof(info)
            if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
                return int(info.i64Size), int(info.i64NumItems)
    except Exception:
        pass
    return None


def _empty_recycle_bin() -> Tuple[int, int, int]:
    if not wu.IS_WIN:
        return 0, 0, 0
    before = _recycle_query() or (0, 0)
    try:
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)  # no confirm, no UI, no sound
    except Exception:
        return 0, 0, 1
    if result == 0:
        return before[0], before[1], 0
    return 0, 0, (0 if before[1] == 0 else 1)


# --------------------------------------------------------------------------- public API


def scan(cat: Category, include_recent: bool = False) -> Tuple[int, int]:
    """Return (bytes, files) that clean() would remove. Deletes nothing."""
    if cat.recycle:
        return _recycle_query() or (0, 0)
    cutoff = _cutoff(cat, include_recent)
    total = count = 0
    for root in _valid_roots(cat):
        for _path, size in _walk_files(root, cutoff):
            total += size
            count += 1
    return total, count


def clean(cat: Category, include_recent: bool = False) -> Tuple[int, int, int]:
    """Delete the files scan() found. Returns (bytes freed, files deleted, files skipped)."""
    if cat.recycle:
        return _empty_recycle_bin()
    cutoff = _cutoff(cat, include_recent)
    freed = deleted = skipped = 0
    for root in _valid_roots(cat):
        folders = _snapshot_dirs(root)
        for path, size in list(_walk_files(root, cutoff)):
            try:
                try:
                    os.chmod(path, stat.S_IWRITE)  # clear the read-only flag
                except OSError:
                    pass
                os.remove(path)
                freed += size
                deleted += 1
            except OSError:
                skipped += 1  # in use or no permission: leave it
        _prune_empty_dirs(folders, cutoff)
    return freed, deleted, skipped
