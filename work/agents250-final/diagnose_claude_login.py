"""Trace only exception types/source locations for the actual access-only mirror."""

import json
import os
import subprocess
import sys
from pathlib import Path

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
    events = []

    def trace(frame, event, arg):
        file = frame.f_code.co_filename.replace("\\", "/")
        if event == "exception" and (
            "/py_docker/" in file or "/laomedo/agents/agents/claude/auth/" in file
        ):
            events.append(
                {
                    "file": (
                        file.split("/site-packages/")[-1]
                        if "/site-packages/" in file
                        else file.split("/src/")[-1]
                    ),
                    "line": frame.f_lineno,
                    "function": frame.f_code.co_name,
                    "exception_type": arg[0].__name__,
                }
            )
        return trace

    outcome = {"ready": False, "submitted_turns": 0}
    sys.settrace(trace)
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
        outcome["ready"] = True
    except Exception as error:
        outcome["error_type"] = type(error).__name__
        if type(error).__name__ == "LocalClaudeLoginError":
            outcome["code"] = str(error)
    finally:
        sys.settrace(None)
    outcome["safe_exception_locations"] = events
    (e / "claude-login-diagnosis.json").write_text(
        json.dumps(outcome, indent=2), encoding="utf-8"
    )
    print(json.dumps(outcome))


if __name__ == "__main__":
    main()
