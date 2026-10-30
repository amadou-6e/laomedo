"""Read native security descriptors without localized ACL output parsing."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct

from laomedo.host.private_state.errors import PrivateStateError


class WindowsDirectorySecurity:
    """Own typed Win32 calls; never expose native diagnostics or change ACLs.

    Descriptor and SID buffers are released with LocalFree in the same method.
    Native ABI values are explicit Win32 types, not application domain records.
    """

    def __init__(self) -> None:
        """Bind the documented native functions only on Windows."""
        if os.name != "nt":
            raise PrivateStateError("windows_private_state_unavailable")
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._security = ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.c_void_p
        pointer_out = ctypes.POINTER(pointer)
        self._kernel.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        self._kernel.GetSystemDirectoryW.restype = wintypes.UINT
        self._kernel.LocalFree.argtypes = [pointer]
        self._kernel.LocalFree.restype = pointer
        self._security.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, pointer_out]
        self._security.ConvertStringSidToSidW.restype = wintypes.BOOL
        self._security.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            pointer_out,
            pointer_out,
            pointer_out,
            pointer_out,
            pointer_out,
        ]
        self._security.GetNamedSecurityInfoW.restype = wintypes.DWORD
        self._security.GetSecurityDescriptorControl.argtypes = [
            pointer,
            ctypes.POINTER(wintypes.WORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._security.GetSecurityDescriptorControl.restype = wintypes.BOOL
        self._security.GetAclInformation.argtypes = [
            pointer,
            pointer,
            wintypes.DWORD,
            ctypes.c_int,
        ]
        self._security.GetAclInformation.restype = wintypes.BOOL
        self._security.GetAce.argtypes = [pointer, wintypes.DWORD, pointer_out]
        self._security.GetAce.restype = wintypes.BOOL
        self._security.IsValidAcl.argtypes = [pointer]
        self._security.IsValidAcl.restype = wintypes.BOOL
        self._security.IsValidSid.argtypes = [pointer]
        self._security.IsValidSid.restype = wintypes.BOOL
        self._security.EqualSid.argtypes = [pointer, pointer]
        self._security.EqualSid.restype = wintypes.BOOL

    def system_directory(self) -> Path:
        """Return the actual system directory without trusting PATH or profile data."""
        buffer = ctypes.create_unicode_buffer(32768)
        count = self._kernel.GetSystemDirectoryW(buffer, len(buffer))
        if not count or count >= len(buffer):
            raise PrivateStateError("private_state_system_directory_unverified")
        result = Path(buffer.value)
        if not result.is_absolute():
            raise PrivateStateError("private_state_system_directory_unverified")
        return result

    def verify(self, path: Path, expected_sid: str) -> None:
        """Require current ownership and a protected, inheritable owner-only DACL.

        References
        ----------
        https://learn.microsoft.com/windows/win32/api/aclapi/nf-aclapi-getnamedsecurityinfow
        https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-access_allowed_ace
        """
        expected = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        owner = ctypes.c_void_p()
        acl = ctypes.c_void_p()
        try:
            if not self._security.ConvertStringSidToSidW(
                expected_sid, ctypes.byref(expected)
            ):
                raise PrivateStateError("private_state_permissions_unverified")
            result = self._security.GetNamedSecurityInfoW(
                str(path),
                1,
                0x01 | 0x04,
                ctypes.byref(owner),
                None,
                ctypes.byref(acl),
                None,
                ctypes.byref(descriptor),
            )
            if result or not descriptor or not owner or not acl:
                raise PrivateStateError("private_state_permissions_unverified")
            if not self._security.IsValidSid(owner) or not self._security.EqualSid(
                owner, expected
            ):
                raise PrivateStateError("private_state_permissions_unverified")
            control = wintypes.WORD()
            revision = wintypes.DWORD()
            if (
                not self._security.GetSecurityDescriptorControl(
                    descriptor, ctypes.byref(control), ctypes.byref(revision)
                )
                or not control.value & 0x1000
            ):
                raise PrivateStateError("private_state_permissions_unverified")
            size_info = (wintypes.DWORD * 3)()
            if (
                not self._security.IsValidAcl(acl)
                or not self._security.GetAclInformation(
                    acl, ctypes.byref(size_info), ctypes.sizeof(size_info), 2
                )
                or size_info[0] == 0
            ):
                raise PrivateStateError("private_state_permissions_unverified")
            for index in range(size_info[0]):
                ace = ctypes.c_void_p()
                if not self._security.GetAce(acl, index, ctypes.byref(ace)) or not ace:
                    raise PrivateStateError("private_state_permissions_unverified")
                kind, flags, length = struct.unpack("<BBH", ctypes.string_at(ace, 4))
                # Only ordinary allow ACEs, propagating full access to files and
                # subdirectories, can satisfy this deliberately narrow policy.
                if kind != 0 or length < 16 or flags & 3 != 3 or flags & 0x0C:
                    raise PrivateStateError("private_state_permissions_unverified")
                mask = struct.unpack("<I", ctypes.string_at(ace.value + 4, 4))[0]
                sid_head = ctypes.string_at(ace.value + 8, 8)
                if length < 16 + 4 * sid_head[1] or mask & 0x1F01FF != 0x1F01FF:
                    raise PrivateStateError("private_state_permissions_unverified")
                sid = ctypes.c_void_p(ace.value + 8)
                if not self._security.IsValidSid(sid) or not self._security.EqualSid(
                    sid, expected
                ):
                    raise PrivateStateError("private_state_permissions_unverified")
        finally:
            if descriptor:
                self._kernel.LocalFree(descriptor)
            if expected:
                self._kernel.LocalFree(expected)
