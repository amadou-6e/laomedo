"""Implementation owned by agents / workflow / utils."""

from __future__ import annotations

from hashlib import sha256
import json


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value):
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


def runner_attempt_terminal(record):
    """End of a runner attempt is separate from an unknown work outcome."""
    return (
        record.get("status")
        in {"completed", "cancelled", "failed", "timeout", "interrupted"}
        or record.get("status") == "unknown"
        and record.get("attempt_finished") is True
    )
