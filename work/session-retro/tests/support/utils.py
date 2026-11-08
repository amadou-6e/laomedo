"""Internal native records; no actual user or provider execution evidence."""

import json


def meta() -> bytes:
    """Return one small explicit internal-session identity record."""
    return record("session_meta", {"id": "internal-session"})


def record(outer, payload) -> bytes:
    """Encode one complete physical Codex-shaped record for internal controls."""
    return (
        json.dumps(
            {"timestamp": "2026-01-01T00:00:00Z", "type": outer, "payload": payload}
        )
        + "\n"
    ).encode()
