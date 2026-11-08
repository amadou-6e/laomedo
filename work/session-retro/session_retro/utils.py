"""Shared-read source handles; never alter Codex writer state."""

import ctypes
import os
from pathlib import Path
from typing import BinaryIO


def open_source(path: Path) -> BinaryIO:
    """Open native bytes read-only, permitting Windows write/delete sharing.

    The caller owns the returned handle. No credential, login or sibling file is
    opened. Errors retain normal filesystem categories for the CLI boundary.
    """
    if os.name != "nt":
        return path.open("rb")
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x80000000, 7, None, 3, 0x08000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(wintypes.HANDLE(handle))
        raise
    return os.fdopen(fd, "rb")
