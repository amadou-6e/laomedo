"""Job-accounted descendant ownership, without another process launcher."""

import ctypes
from ctypes.wintypes import BOOL, DWORD, HANDLE, LPCWSTR
import time

from .models import NativeJobAccounting, NativeJobLimits, NativeThreadEntry
from .settings import (
    ERROR_NO_MORE_FILES,
    JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    TH32CS_SNAPTHREAD,
    THREAD_QUERY_LIMITED_INFORMATION,
    THREAD_SUSPEND_RESUME,
)


class WindowsProcessTree:
    """Contain an exact suspended root and all CreateProcess descendants.

    No breakaway is admitted. Assignment failures remain failures; this object
    never falls back to an uncontained launch or infers cleanup from a root PID.
    """

    def __init__(self):
        self._native = ctypes.WinDLL("kernel32", use_last_error=True)
        self._bind()
        self._job = self._native.CreateJobObjectW(None, None)
        self._attached = False
        if not self._job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = NativeJobLimits()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._native.SetInformationJobObject(
            self._job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def _bind(self):
        """Declare pointer-width-safe signatures for this fixed Win32 boundary."""
        native = self._native
        native.CreateJobObjectW.argtypes = [ctypes.c_void_p, LPCWSTR]
        native.CreateJobObjectW.restype = HANDLE
        native.SetInformationJobObject.argtypes = [
            HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            DWORD,
        ]
        native.SetInformationJobObject.restype = BOOL
        native.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
        native.AssignProcessToJobObject.restype = BOOL
        native.QueryInformationJobObject.argtypes = [
            HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            DWORD,
            ctypes.c_void_p,
        ]
        native.QueryInformationJobObject.restype = BOOL
        native.TerminateJobObject.argtypes = [HANDLE, DWORD]
        native.TerminateJobObject.restype = BOOL
        native.CreateToolhelp32Snapshot.argtypes = [DWORD, DWORD]
        native.CreateToolhelp32Snapshot.restype = HANDLE
        native.Thread32First.argtypes = [HANDLE, ctypes.POINTER(NativeThreadEntry)]
        native.Thread32First.restype = BOOL
        native.Thread32Next.argtypes = [HANDLE, ctypes.POINTER(NativeThreadEntry)]
        native.Thread32Next.restype = BOOL
        native.OpenThread.argtypes = [DWORD, BOOL, DWORD]
        native.OpenThread.restype = HANDLE
        native.GetProcessIdOfThread.argtypes = [HANDLE]
        native.GetProcessIdOfThread.restype = DWORD
        native.ResumeThread.argtypes = [HANDLE]
        native.ResumeThread.restype = DWORD
        native.CloseHandle.argtypes = [HANDLE]
        native.CloseHandle.restype = BOOL

    def attach(self, process):
        """Bind the Popen-owned, still-suspended root handle before any code runs."""
        if self._attached:
            raise OSError("The owned job already has a root")
        if not self._native.AssignProcessToJobObject(self._job, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._attached = True

    def resume(self, pid):
        """Resume the sole suspended primary thread only after job assignment."""
        if not self._attached:
            raise OSError("The suspended root has not been assigned")
        snapshot = self._native.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            threads = []
            entry = NativeThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            available = self._native.Thread32First(snapshot, ctypes.byref(entry))
            while available:
                if entry.th32OwnerProcessID == pid:
                    threads.append(entry.th32ThreadID)
                entry.dwSize = ctypes.sizeof(entry)
                available = self._native.Thread32Next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != ERROR_NO_MORE_FILES or len(threads) != 1:
                raise OSError(
                    "The suspended root's sole primary thread was not verified"
                )
            thread = self._native.OpenThread(
                THREAD_SUSPEND_RESUME | THREAD_QUERY_LIMITED_INFORMATION,
                False,
                threads[0],
            )
            if not thread:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if self._native.GetProcessIdOfThread(thread) != pid:
                    raise OSError("The suspended thread owner changed")
                if self._native.ResumeThread(thread) != 1:
                    raise OSError(
                        "The primary thread did not have one suspended reference"
                    )
            finally:
                self._native.CloseHandle(thread)
        finally:
            self._native.CloseHandle(snapshot)

    def active_processes(self):
        """Query the owned job, including nested jobs, without enumerating other jobs."""
        accounting = NativeJobAccounting()
        if not self._native.QueryInformationJobObject(
            self._job,
            JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return accounting.ActiveProcesses

    def terminate(self, deadline):
        """Confirm zero active processes under the caller's unchanged cleanup deadline."""
        if self.active_processes() == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        if not self._native.TerminateJobObject(self._job, 1):
            return False
        while self.active_processes():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.01, remaining))
        return True

    def close(self):
        """Release this non-inherited job handle; kill-on-close is a safety backstop.

        Closing never counts as termination proof. Only observed empty accounting
        may establish confirmed cleanup before the caller returns success.
        """
        if self._job is not None:
            if not self._native.CloseHandle(self._job):
                return False
            self._job = None
        return True
