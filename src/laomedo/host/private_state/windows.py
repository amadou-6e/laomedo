"""Owner-only directory security through the runner's existing pywin32 dependency."""

import os
from pathlib import Path

from laomedo.host.private_state.errors import PrivateStateError


class WindowsDirectorySecurity:
    """Use managed native descriptors; never parse localized permission output.

    pywin32 is already required by Docker's Windows transport. Lazy symbol
    imports keep the base SIWC mechanism available without the runner extra.
    Native descriptors remain native objects, never application payloads.
    """

    def __init__(self) -> None:
        """Refuse unsupported platforms before importing Windows-only packages."""
        if os.name != "nt":
            raise PrivateStateError("windows_private_state_unavailable")

    def system_directory(self) -> Path:
        """Resolve the actual system directory without trusting PATH."""
        try:
            from win32api import GetSystemDirectory

            result = Path(GetSystemDirectory())
            if not result.is_absolute():
                raise ValueError()
            return result
        except Exception:
            raise PrivateStateError(
                "private_state_system_directory_unverified"
            ) from None

    def _read(self, path: Path):
        """Read owner and DACL only, without requesting audit privileges."""
        from win32security import DACL_SECURITY_INFORMATION, OWNER_SECURITY_INFORMATION
        from win32security import GetNamedSecurityInfo, SE_FILE_OBJECT

        return GetNamedSecurityInfo(
            str(path),
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        )

    def restrict(self, path: Path, expected_sid: str) -> None:
        """Replace only a newly created, current-user-owned leaf's DACL.

        Retaining explicit ACEs from mkdir/icacls can leave other principals
        admitted. Build one inheritable owner ACE, protect it, then let the
        caller independently verify the resulting descriptor. Never take owner.
        """
        try:
            from ntsecuritycon import FILE_ALL_ACCESS
            from win32con import CONTAINER_INHERIT_ACE, OBJECT_INHERIT_ACE
            from win32security import ACL, ACL_REVISION, ConvertStringSidToSid
            from win32security import (
                DACL_SECURITY_INFORMATION,
                PROTECTED_DACL_SECURITY_INFORMATION,
            )
            from win32security import SE_FILE_OBJECT, SetNamedSecurityInfo

            expected = ConvertStringSidToSid(expected_sid)
            if self._read(path).GetSecurityDescriptorOwner() != expected:
                raise ValueError()
            acl = ACL()
            acl.AddAccessAllowedAceEx(
                ACL_REVISION,
                OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE,
                FILE_ALL_ACCESS,
                expected,
            )
            SetNamedSecurityInfo(
                str(path),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                acl,
                None,
            )
        except Exception:
            raise PrivateStateError("private_state_permissions_unverified") from None

    def verify(self, path: Path, expected_sid: str) -> None:
        """Require current ownership and protected, inheritable owner-only access.

        https://mhammond.github.io/pywin32/PyACL__GetAce_meth.html
        """
        try:
            from ntsecuritycon import FILE_ALL_ACCESS
            from win32con import CONTAINER_INHERIT_ACE, OBJECT_INHERIT_ACE
            from win32con import INHERIT_ONLY_ACE, NO_PROPAGATE_INHERIT_ACE
            from win32security import ACCESS_ALLOWED_ACE_TYPE, ConvertStringSidToSid
            from win32security import SE_DACL_PROTECTED

            expected = ConvertStringSidToSid(expected_sid)
            descriptor = self._read(path)
            if descriptor.GetSecurityDescriptorOwner() != expected:
                raise ValueError()
            if not descriptor.GetSecurityDescriptorControl()[0] & SE_DACL_PROTECTED:
                raise ValueError()
            acl = descriptor.GetSecurityDescriptorDacl()
            if acl is None or acl.GetAceCount() == 0:
                raise ValueError()
            required = OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
            refused = INHERIT_ONLY_ACE | NO_PROPAGATE_INHERIT_ACE
            for index in range(acl.GetAceCount()):
                header, mask, sid = acl.GetAce(index)
                kind, flags = header
                if (
                    kind != ACCESS_ALLOWED_ACE_TYPE
                    or flags & required != required
                    or flags & refused
                    or mask & FILE_ALL_ACCESS != FILE_ALL_ACCESS
                    or sid != expected
                ):
                    raise ValueError()
        except Exception:
            raise PrivateStateError("private_state_permissions_unverified") from None
