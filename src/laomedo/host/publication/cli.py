"""Implementation owned by host / publication / cli."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import secrets
import threading
import time


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


def main():
    # Explicitly refuse ambient provider overrides rather than falling back.
    import laomedo.host.publication.verifier as _publication_verifier

    if any(
        key in os.environ
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_LAOMEDO", "GH", "GIT_ASKPASS")
    ):
        raise ValueError("verifier_credential_environment_denied")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-state", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--agent-mount", type=Path, required=True)
    parser.add_argument("--baseline-bundle", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    args = parser.parse_args()
    worker = _publication_verifier.BundleVerifier(**vars(args))
    try:
        worker.serve(threading.Event())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
