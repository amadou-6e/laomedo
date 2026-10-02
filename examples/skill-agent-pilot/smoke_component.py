"""Credential-free smoke check for the pinned Langflow custom component."""

import io
import json
import os
from pathlib import Path
import tempfile
from urllib import error

import langflow_component

private = tempfile.TemporaryDirectory()
token_path = Path(private.name) / "api-token"
token_path.write_text("a" * 64, encoding="utf-8")
os.environ["LAOMEDO_RUNNER_TOKEN_FILE"] = str(token_path)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


component = langflow_component.LaomedoRunner()
component.task = "Read the fixture"
component.skill_id = "laomedo-pilot"
component.revision_id = "sha256:" + "a" * 64
component.model = "gpt-6-luna"
component.effort = "low"


def success(req, timeout):
    assert req.get_header("Authorization") == "Bearer " + "a" * 64
    payload = json.loads(req.data)
    assert payload["task"] == "Read the fixture"
    assert payload["skill_ref"]["revision_id"] == component.revision_id
    return Response(json.dumps({"status": "completed", "answer": "amber 3",
        "run_id": "fixture-run", "thread_id": "fixture-thread",
        "skill": {"revision_id": component.revision_id,
                  "use_evidence": "offered"},
        "raw_event_ref": "laomedo:run:fixture-run:events"}).encode())


langflow_component.request.urlopen = success
result = component.invoke().data
assert result["answer"] == "amber 3"
assert result["run_id"] == "fixture-run"
assert result["usage"] == "unknown"


def failure(req, timeout):
    data = json.dumps({"status": "timeout", "run_id": "failed-run",
                       "error_category": "turn_timeout"}).encode()
    raise error.HTTPError(req.full_url, 502, "failed", {}, Response(data))


langflow_component.request.urlopen = failure
try:
    component.invoke()
except RuntimeError as exc:
    assert "failed-run" in str(exc)
    assert "turn_timeout" in str(exc)
else:
    raise AssertionError("failed run became a successful component result")

private.cleanup()
print("component_success_and_failure_paths_passed")
