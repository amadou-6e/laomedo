"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

TERMINAL = frozenset(
    {"completed", "rejected", "failed", "unknown", "expired", "cancelled"}
)
