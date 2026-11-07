"""Actual concurrent access-only copies, reporting no credential contents."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
from threading import Barrier
import time

from laomedo.agents.agents.claude.auth.utils import mirror_login


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    e = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((e / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    image = subprocess.check_output(
        [
            "docker",
            "image",
            "inspect",
            "laomedo-claude-controller:2.1.310-acp0.98.0",
            "--format",
            "{{.Id}}",
        ],
        text=True,
    ).strip()
    gate = Barrier(2)

    def copy(_):
        gate.wait()
        start = time.monotonic()
        try:
            mirror_login(
                "laomedo-claude-profile",
                image,
                environment=os.environ
                | {
                    "LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN": "1",
                    "LAOMEDO_CLAUDE_LOGIN_STATE_DIR": str(state / "claude-login"),
                },
            )
            return {
                "ready": True,
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }
        except Exception as error:
            return {
                "ready": False,
                "error_type": type(error).__name__,
                "code": (
                    str(error)
                    if type(error).__name__ == "LocalClaudeLoginError"
                    else None
                ),
            }

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(copy, range(2)))
    result = {
        "copies": results,
        "submitted_turns": 0,
        "scope": "Actual SDK-owned helper copies; access only, no refresh ownership, no retry.",
    }
    (e / "claude-parallel-copy-fixed.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))
    if not all(r["ready"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
