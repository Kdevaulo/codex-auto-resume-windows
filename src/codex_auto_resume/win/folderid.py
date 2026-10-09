"""Which folder a path names, whatever it is spelled as (v0.6.14-beta.2).

A Codex home's lock is named by its path (win/homelock.py), and one folder can be spelled more than one
way - a junction, a subst drive, a symbolic link, a share of the same disk. Windows gives every folder on
a volume an index that does not change with the spelling: GetFileInformationByHandle on the folder
itself, opened with FILE_FLAG_BACKUP_SEMANTICS (which a folder needs), answers the volume's serial number
and that index. The two together name the folder, so a second lock named by them makes one folder one
home however it was named. Read only: the folder is opened for its attributes, never for its contents,
shared for everything, and closed at once.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os

FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE = W.HANDLE(-1).value


class _Information(C.Structure):
    _fields_ = [("dwFileAttributes", W.DWORD), ("ftCreationTime", W.FILETIME),
                ("ftLastAccessTime", W.FILETIME), ("ftLastWriteTime", W.FILETIME),
                ("dwVolumeSerialNumber", W.DWORD), ("nFileSizeHigh", W.DWORD), ("nFileSizeLow", W.DWORD),
                ("nNumberOfLinks", W.DWORD), ("nFileIndexHigh", W.DWORD), ("nFileIndexLow", W.DWORD)]


def _api():
    k = C.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    k.CreateFileW.restype = W.HANDLE
    k.GetFileInformationByHandle.argtypes = [W.HANDLE, C.POINTER(_Information)]
    k.GetFileInformationByHandle.restype = W.BOOL
    k.CloseHandle.argtypes = [W.HANDLE]
    k.CloseHandle.restype = W.BOOL
    return k


def identity(path) -> str | None:
    """`<volume serial>-<file index>` of the folder `path` names, as 8 and 16 lowercase hex digits - or
    None where it cannot be told: not Windows, no such folder, a file, or a folder Windows will not open."""
    if os.name != "nt":
        return None
    try:
        if not os.path.isdir(path):
            return None
        k = _api()
    except (OSError, TypeError, ValueError):
        return None
    handle = k.CreateFileW(str(path), FILE_READ_ATTRIBUTES, FILE_SHARE_ALL, None, OPEN_EXISTING,
                           FILE_FLAG_BACKUP_SEMANTICS, None)
    if not handle or handle == INVALID_HANDLE:
        return None
    try:
        found = _Information()
        if not k.GetFileInformationByHandle(handle, C.byref(found)):
            return None
        if not found.dwFileAttributes & 0x10:          # FILE_ATTRIBUTE_DIRECTORY
            return None
        return "%08x-%016x" % (found.dwVolumeSerialNumber, (found.nFileIndexHigh << 32) | found.nFileIndexLow)
    finally:
        k.CloseHandle(handle)
