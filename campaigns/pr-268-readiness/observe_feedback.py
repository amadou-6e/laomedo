"""Run the authorized check while exposing only runner outcome categories."""

import json
import io
import os
import runpy
import sys
from pathlib import Path
from urllib import request, error

import langflow
from lfx.services.deps import get_settings_service
from laomedo.agents.handoffs.transport import RunnerAdapter


def observe_dispatch(self, *args, **kwargs):
    result = original_dispatch(self, *args, **kwargs)
    print(
        json.dumps(
            {
                "runner_outcome": {
                    key: result.get(key)
                    for key in ("status", "error_category", "run_id")
                }
            }
        )
    )
    return result


def observe_open(self, *args, **kwargs):
    try:
        return original_open(self, *args, **kwargs)
    except error.HTTPError as exc:
        if exc.url.startswith("http://127.0.0.1:8765/"):
            raw = exc.read()
            exc.fp = io.BytesIO(raw)
            try:
                category = json.loads(raw).get("error_category")
            except (ValueError, AttributeError):
                category = "non_json_error"
            print(
                json.dumps(
                    {"runner_http_status": exc.code, "runner_error_category": category}
                )
            )
        raise


get_settings_service()
original_dispatch = RunnerAdapter.dispatch
RunnerAdapter.dispatch = observe_dispatch
original_open = request.OpenerDirector.open
request.OpenerDirector.open = observe_open
sys.argv = [
    "live_feedback.py",
    "--checkout",
    "C:/CodeWorkspace/laomedo/.tools/worktrees/pr-268",
    "--approval-file",
    os.environ["PR268_APPROVAL_PATH"],
]
runpy.run_path(str(Path(__file__).with_name("live_feedback.py")), run_name="__main__")
