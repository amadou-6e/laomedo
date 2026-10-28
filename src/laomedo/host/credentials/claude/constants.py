"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

CODES = frozenset(
    {
        "claude_host_login_unavailable",
        "claude_host_login_expired",
        "claude_local_login_copy_failed",
    }
)
