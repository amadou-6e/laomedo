"""Persist private publication service diagnostics atomically."""

from pathlib import Path
import json, os, secrets, time


def _publish_status(path: Path, value: dict) -> None:
    # Diagnostic writes must not reuse a pending path left by a killed
    # process. Verification reservations still use their immutable one-shot
    # journals; this status cannot authorize/restart an attempt.
    pending = path.with_name(path.name + ".pending-" + secrets.token_hex(8))
    try:
        with pending.open("x", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(value, sort_keys=True) + "\n")
        for attempt in range(20):
            try:
                os.replace(pending, path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)
    finally:
        pending.unlink(missing_ok=True)
