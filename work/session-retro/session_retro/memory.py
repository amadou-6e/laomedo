"""Peak single-process resident memory without starting a monitoring service."""

import ctypes
import os
import sys


class WindowsMemoryCounters(ctypes.Structure):
    """Windows PROCESS_MEMORY_COUNTERS ABI, local process metadata only.

    This ctypes FFI layout is intentionally not a Pydantic domain model: its
    native memory layout must match the OS structure exactly.
    """

    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage",
            "PagefileUsage",
            "PeakPagefileUsage",
        )
    ]


class ProcessMemory:
    """Measure the current process; the reader creates no child processes."""

    @staticmethod
    def peak() -> int:
        """Measure this process's high-water resident memory.

        Returns
        -------
        int
            OS-reported peak resident bytes; not a sum of child process memory.

        Raises
        ------
        OSError
            The native memory-information query fails.

        Notes
        -----
        Does not start a sampler or subprocess; never invents zero on failure.
        """
        if os.name == "nt":
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            counters = WindowsMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(
                kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return counters.PeakWorkingSetSize
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak * (1 if sys.platform == "darwin" else 1024))
