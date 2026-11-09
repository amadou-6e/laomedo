"""Shared-read source handles; never alter Codex writer state."""

import ctypes
import os
from pathlib import Path
from typing import BinaryIO


def open_source(path: Path) -> BinaryIO:
    """Open an original source read-only without blocking an active writer.

    Parameters
    ----------
    path : Path
        Explicit selected source; no recursive discovery is performed.

    Returns
    -------
    BinaryIO
        Owned binary handle; caller must close it, normally with a context manager.

    Raises
    ------
    OSError
        File open fails; no source or profile mutation is attempted.

    Notes
    -----
    Windows uses shared read/write/delete access. Other platforms use ordinary rb.
    The caller verifies identity/hash; opening alone does not authenticate evidence.
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
