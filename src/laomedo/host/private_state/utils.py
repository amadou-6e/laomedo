"""Generic permission effects and strict lexical private-directory admission."""

import csv
import os
from pathlib import Path
import stat
import subprocess
import time

from laomedo.host.private_state.errors import PrivateStateError
from laomedo.host.private_state.models import (
    DirectoryPermissionPolicy,
    DirectoryPermissionResult,
)
from laomedo.host.private_state.windows import WindowsDirectorySecurity


def _run(
    arguments: list[str], ceiling: float, policy: DirectoryPermissionPolicy | None
):
    """Preserve legacy subprocess kwargs unless an explicit strict policy is supplied."""
    options = {"capture_output": True, "text": True, "timeout": ceiling}
    if policy is not None:
        options["env"] = policy.environment
        options["timeout"] = policy.timeout_seconds(ceiling, time.monotonic())
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(arguments, **options)


def _owner_sid(policy: DirectoryPermissionPolicy | None) -> str:
    """Read the current SID with unchanged legacy CSV admission."""
    identity = _run(
        [str(policy.whoami) if policy else "whoami", "/user", "/fo", "csv", "/nh"],
        10,
        policy,
    )
    if identity.returncode:
        raise PrivateStateError("private_state_permissions_unverified")
    rows = list(csv.reader(identity.stdout.splitlines()))
    if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].startswith("S-"):
        raise PrivateStateError("private_state_permissions_unverified")
    return rows[0][1]


def restrict_directory(
    path: Path, *, policy: DirectoryPermissionPolicy | None = None
) -> DirectoryPermissionResult:
    """Apply the original chmod/icacls mechanism; callers own strict verification.

    Native OSError and TimeoutExpired deliberately retain their original types.
    The compatibility caller translates only PrivateStateError policy failures.
    """
    if os.name != "nt":
        os.chmod(path, 0o700)
        return DirectoryPermissionResult()
    sid = _owner_sid(policy)
    result = _run(
        [
            str(policy.icacls) if policy else "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            "*" + sid + ":(OI)(CI)F",
        ],
        15,
        policy,
    )
    if result.returncode:
        raise PrivateStateError("private_state_permissions_unverified")
    return DirectoryPermissionResult(owner_sid=sid)


def validate_private_path(path: Path) -> None:
    """Refuse lexical links/reparse points, relative traversal and checkout paths."""
    if not path.is_absolute() or ".." in path.parts or path.drive.startswith("\\\\"):
        raise PrivateStateError("private_state_path_unverified")
    for parent in (path, *path.parents):
        try:
            observed = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(observed.st_mode) or getattr(
            observed, "st_file_attributes", 0
        ) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise PrivateStateError("private_state_link_rejected")
        if not stat.S_ISDIR(observed.st_mode):
            raise PrivateStateError("private_state_path_unverified")
        if os.path.lexists(parent.joinpath(".git")):
            raise PrivateStateError("private_state_inside_checkout")


def prepare_private_directory(
    path: Path, *, policy: DirectoryPermissionPolicy | None = None
) -> None:
    """Create/restrict only a new owned leaf; verify existing leaves without mutation."""
    validate_private_path(path)
    created = False
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
        created = True
    except FileExistsError:
        pass
    validate_private_path(path)
    if os.name == "nt":
        if policy is None:
            raise PrivateStateError("private_state_policy_required")
        identity = DirectoryPermissionResult(owner_sid=_owner_sid(policy))
        if identity.owner_sid is None:
            raise PrivateStateError("private_state_permissions_unverified")
        security = WindowsDirectorySecurity()
        if created:
            policy.timeout_seconds(20.0, time.monotonic())
            security.restrict(path, identity.owner_sid)
        security.verify(path, identity.owner_sid)
    else:
        observed = path.lstat()
        if observed.st_uid != os.getuid() or stat.S_IMODE(observed.st_mode) != 0o700:
            raise PrivateStateError("private_state_permissions_unverified")
    validate_private_path(path)
