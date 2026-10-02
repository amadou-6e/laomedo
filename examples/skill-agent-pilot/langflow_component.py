"""Langflow 1.12.3 local Laomedo handoff.

The built-in API Request component returns an ordinary Data value for HTTP
and connection failures. This component raises a Langflow error with the run ID
when the runner reports a failed turn, so a failed agent is not a chat answer.
"""

import json
import os
from pathlib import Path
import re
from urllib import error, request

from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, StrInput, Output
from lfx.schema import Data


class LaomedoRunner(Component):
    display_name = "Laomedo Skill Agent"
    description = "Run one pinned whole-skill Codex turn on the local runner."
    icon = "Workflow"
    name = "LaomedoRunner"

    inputs = [
        MessageTextInput(name="task", display_name="Task", required=True),
        StrInput(name="skill_id", display_name="Skill ID", required=True),
        StrInput(name="revision_id", display_name="Skill Revision", required=True),
        StrInput(name="model", display_name="Model", value="gpt-6-luna"),
        StrInput(name="effort", display_name="Effort", value="low"),
    ]
    outputs = [Output(display_name="Run Result", name="result", method="invoke")]

    def invoke(self) -> Data:
        task = getattr(self.task, "text", self.task)
        payload = {
            "task": str(task), "model": str(self.model), "effort": str(self.effort),
            "skill_ref": {"skill_id": str(self.skill_id),
                          "revision_id": str(self.revision_id),
                          "tree_hash": str(self.revision_id)},
        }
        endpoint = "http://host.docker.internal:8765/v1/runs"
        token_file = os.environ.get("LAOMEDO_RUNNER_TOKEN_FILE",
                                    "/run/secrets/laomedo-runner-token")
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            raise RuntimeError("Laomedo runner API token file is unavailable") from None
        if not re.fullmatch(r"[0-9a-f]{64}", token):
            raise RuntimeError("Laomedo runner API token file is invalid")
        req = request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json",
                                       "Authorization": "Bearer " + token},
                              method="POST")
        try:
            with request.urlopen(req, timeout=210) as response:
                result = json.load(response)
        except error.HTTPError as exc:
            try:
                result = json.load(exc)
            except (ValueError, TypeError):
                raise RuntimeError("Laomedo runner returned invalid error data") from exc
        except (error.URLError, TimeoutError, OSError):
            raise RuntimeError("Laomedo runner connection failed; run may still complete") from None
        if not isinstance(result, dict):
            raise RuntimeError("Laomedo runner returned invalid data")
        run_id = result.get("run_id")
        if result.get("status") != "completed":
            category = result.get("error_category") or result.get("status") or "unknown"
            raise RuntimeError(f"Laomedo run {run_id or 'unknown'} failed: {category}")
        skill = result.get("skill")
        if (not isinstance(run_id, str) or not run_id or
                not isinstance(skill, dict) or
                not isinstance(skill.get("revision_id"), str) or
                not isinstance(skill.get("use_evidence"), str) or
                not isinstance(result.get("raw_event_ref"), str)):
            raise RuntimeError("Laomedo runner returned invalid completed data")
        data = {"answer": result.get("answer"), "run_id": run_id,
                "thread_id": result.get("thread_id"), "status": result["status"],
                "skill_revision": skill["revision_id"],
                "skill_use_evidence": skill["use_evidence"],
                "trace_ref": result["raw_event_ref"],
                "usage": "unknown"}
        self.status = f"Laomedo run {run_id} completed"
        return Data(data=data)
