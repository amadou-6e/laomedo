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


def exec_output(exit_code: int | None, output: str) -> list[dict]:
    """Construct the observed outer native envelope, keeping stdout opaque."""
    envelope = {"chunk_id": "internal", "wall_time_seconds": 1.0, "output": output}
    if exit_code is not None:
        envelope["exit_code"] = exit_code
    return [
        {
            "type": "input_text",
            "text": "Script completed\nWall time 1.0 seconds\nOutput:\n",
        },
        {"type": "input_text", "text": json.dumps(envelope)},
    ]
