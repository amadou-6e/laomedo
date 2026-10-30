"""Implementation owned by github / transport / git / utils."""

from __future__ import annotations

from pathlib import Path
import stat


def _redirected_path(path: Path) -> bool:
    """Treat links and Windows reparse points as external object sources."""
    try:
        status = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _push_failure_category(stderr: bytes, stdout: bytes = b"") -> str:
    """Return only a fixed diagnostic label, never Git's untrusted output."""
    lower = (stderr + b"\n" + stdout).lower()
    if any(
        marker in lower
        for marker in (
            b"authentication failed",
            b"http 403",
            b"error: 403",
            b"403 forbidden",
            b"permission denied",
            b"permission to",
            b"could not read username",
        )
    ):
        return "authentication_or_authorization"
    if b"remote rejected" in lower or b"pre-receive hook declined" in lower:
        return "remote_rejected"
    if any(
        marker in lower
        for marker in (
            b"could not resolve host",
            b"timed out",
            b"failed to connect",
            b"connection reset",
            b"network is unreachable",
        )
    ):
        return "network_or_transport"
    return "unclassified"
