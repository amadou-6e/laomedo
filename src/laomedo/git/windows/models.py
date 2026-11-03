"""Win32 ABI layouts, not application data or Pydantic serialization models."""

from ctypes import Structure, c_longlong, c_size_t, c_ulonglong
from ctypes.wintypes import DWORD, LONG


class NativeJobBasicLimits(Structure):
    """JOBOBJECT_BASIC_LIMIT_INFORMATION with native pointer-width fields."""

    _fields_ = [
        ("PerProcessUserTimeLimit", c_longlong),
        ("PerJobUserTimeLimit", c_longlong),
        ("LimitFlags", DWORD),
        ("MinimumWorkingSetSize", c_size_t),
        ("MaximumWorkingSetSize", c_size_t),
        ("ActiveProcessLimit", DWORD),
        ("Affinity", c_size_t),
        ("PriorityClass", DWORD),
        ("SchedulingClass", DWORD),
    ]


class NativeIoCounters(Structure):
    """IO_COUNTERS embedded by the native extended job-limit contract."""

    _fields_ = [
        ("ReadOperationCount", c_ulonglong),
        ("WriteOperationCount", c_ulonglong),
        ("OtherOperationCount", c_ulonglong),
        ("ReadTransferCount", c_ulonglong),
        ("WriteTransferCount", c_ulonglong),
        ("OtherTransferCount", c_ulonglong),
    ]


class NativeJobLimits(Structure):
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION; only kill-on-close is enabled."""

    _fields_ = [
        ("BasicLimitInformation", NativeJobBasicLimits),
        ("IoInfo", NativeIoCounters),
        ("ProcessMemoryLimit", c_size_t),
        ("JobMemoryLimit", c_size_t),
        ("PeakProcessMemoryUsed", c_size_t),
        ("PeakJobMemoryUsed", c_size_t),
    ]


class NativeJobAccounting(Structure):
    """JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, including all active descendants."""

    _fields_ = [
        ("TotalUserTime", c_longlong),
        ("TotalKernelTime", c_longlong),
        ("ThisPeriodTotalUserTime", c_longlong),
        ("ThisPeriodTotalKernelTime", c_longlong),
        ("TotalPageFaultCount", DWORD),
        ("TotalProcesses", DWORD),
        ("ActiveProcesses", DWORD),
        ("TotalTerminatedProcesses", DWORD),
    ]


class NativeThreadEntry(Structure):
    """THREADENTRY32: identify only the exact suspended root's primary thread."""

    _fields_ = [
        ("dwSize", DWORD),
        ("cntUsage", DWORD),
        ("th32ThreadID", DWORD),
        ("th32OwnerProcessID", DWORD),
        ("tpBasePri", LONG),
        ("tpDeltaPri", LONG),
        ("dwFlags", DWORD),
    ]
