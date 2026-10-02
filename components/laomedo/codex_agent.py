"""Langflow 1.12.3 custom component for the private local Codex runner."""

import asyncio
import json
import os
from pathlib import Path
import re
from urllib import error, request
from urllib.parse import urlsplit
from uuid import UUID

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, IntInput, MessageTextInput, Output, StrInput
from lfx.schema import Data, Message


class LaomedoCodexAgent(Component):
    display_name = "Laomedo Codex Agent"
    description = "Run or resume a pinned-skill Codex session through the local Docker runner."
    icon = "Bot"
    name = "LaomedoCodexAgent"

    inputs = [
        MessageTextInput(name="task", display_name="Task"),
        DropdownInput(name="operation", display_name="Operation",
                      options=["fresh", "resume", "status", "cancel"], value="fresh"),
        StrInput(name="skill_id", display_name="Skill ID"),
        StrInput(name="revision_id", display_name="Skill Revision"),
        StrInput(name="model", display_name="Model", value="gpt-6-luna"),
        StrInput(name="effort", display_name="Reasoning Effort", value="low"),
        DataInput(name="run_reference", display_name="Prior Run", advanced=True),
        StrInput(name="run_reference_json", display_name="Prior Run JSON", advanced=True,
                 info="For API/manual resume when no Data port is connected."),
        StrInput(name="runner_url", display_name="Runner URL", advanced=True,
                 value="http://host.docker.internal:8765"),
        IntInput(name="timeout_seconds", display_name="HTTP Timeout", value=210,
                 advanced=True),
    ]
    outputs = [
        Output(name="answer", display_name="Answer", method="answer_output", group_outputs=True),
        Output(name="run", display_name="Run Reference", method="run_output", group_outputs=True),
    ]

    def _pre_run_setup(self):
        # Langflow invokes this once per build. Both output methods share dispatch.
        self._dispatch_task = None

    def _prepare(self):
        base = str(self.runner_url).rstrip("/")
        parsed = urlsplit(base)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1", "host.docker.internal"} or
                parsed.username or parsed.password or parsed.path or
                parsed.query or parsed.fragment):
            raise ValueError("local_runner_url_required")
        if not 1 <= int(self.timeout_seconds) <= 240:
            raise ValueError("timeout_must_be_1_to_240_seconds")
        operation = str(self.operation)
        if operation not in {"fresh", "resume", "status", "cancel"}:
            raise ValueError("invalid_operation")
        task = str(getattr(self.task, "text", self.task) or "")
        if operation in {"fresh", "resume"} and not task.strip():
            raise ValueError("task_required")
        model, effort = str(self.model), str(self.effort)
        if operation in {"fresh", "resume"} and (not model.strip() or not effort.strip()):
            raise ValueError("model_and_effort_required")
        if operation == "fresh":
            revision = str(self.revision_id)
            if not str(self.skill_id).strip() or not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
                raise ValueError("pinned_skill_required")
            return base + "/v1/runs", {"task": task, "model": model, "effort": effort,
                "skill_ref": {"skill_id": str(self.skill_id),
                              "revision_id": revision, "tree_hash": revision}}, "POST"
        prior = getattr(self.run_reference, "data", self.run_reference)
        if prior is None and getattr(self, "run_reference_json", None):
            try:
                prior = json.loads(self.run_reference_json)
            except (ValueError, TypeError):
                raise ValueError("invalid_prior_run_json") from None
        if not isinstance(prior, dict):
            raise ValueError("prior_run_required")
        run_id = str(prior.get("run_id", ""))
        try:
            if str(UUID(run_id)) != run_id:
                raise ValueError()
        except ValueError:
            raise ValueError("invalid_run_id") from None
        endpoint = base + "/v1/runs/" + run_id
        if operation == "status":
            return endpoint, None, "GET"
        if operation == "cancel":
            return endpoint + "/cancel", {}, "POST"
        snapshot, thread = prior.get("post_run_hash"), prior.get("thread_id")
        if (prior.get("status") != "completed" or not isinstance(snapshot, str) or
                not re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot) or not thread):
            raise ValueError("completed_snapshot_and_thread_required")
        if prior.get("model") != model or prior.get("effort") != effort:
            raise ValueError("resume_model_effort_mismatch")
        return endpoint + "/resume", {"task": task, "model": model, "effort": effort,
            "expected_post_run_hash": snapshot, "expected_thread_id": thread}, "POST"

    def _http(self, endpoint, payload, method):
        token_file = os.environ.get("LAOMEDO_RUNNER_TOKEN_FILE",
                                    "/run/secrets/laomedo-runner-token")
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            raise RuntimeError("runner_api_token_file_unavailable") from None
        if not token:
            raise RuntimeError("runner_api_token_file_empty")
        req = request.Request(endpoint,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + token}, method=method)
        try:
            with request.urlopen(req, timeout=int(self.timeout_seconds)) as response:
                result = json.load(response)
        except error.HTTPError as exc:
            try:
                result = json.load(exc)
            except (ValueError, TypeError):
                raise RuntimeError("runner_invalid_error_response") from None
            if not isinstance(result, dict):
                raise RuntimeError("runner_invalid_error_response")
            if not (self.operation == "cancel" and result.get("run_id") and
                    result.get("status") in {"completed", "cancelled", "failed", "timeout"}):
                raise RuntimeError("Laomedo run " + str(result.get("run_id") or "unknown") +
                    " failed: " + str(result.get("error_category") or result.get("status") or "unknown")) from None
        except (error.URLError, TimeoutError, OSError):
            raise RuntimeError("runner_transport_failed; remote execution may still be active") from None
        except (ValueError, TypeError):
            raise RuntimeError("runner_invalid_response") from None
        if not isinstance(result, dict) or not result.get("run_id"):
            raise RuntimeError("runner_invalid_response")
        if self.operation in {"fresh", "resume"} and result.get("status") != "completed":
            raise RuntimeError(f"Laomedo run {result['run_id']} failed: "
                               f"{result.get('error_category') or result.get('status') or 'unknown'}")
        skill = result.get("skill") or {}
        return {"answer": result.get("answer"), "run_id": result["run_id"],
            "thread_id": result.get("thread_id"), "status": result.get("status"),
            "post_run_hash": result.get("post_run_hash"),
            "model": result.get("requested_model"), "effort": result.get("requested_effort"),
            "skill_revision": skill.get("revision_id"),
            "skill_use_evidence": skill.get("use_evidence", "unknown"),
            "artifact_ref": result.get("output_ref"), "trace_ref": result.get("raw_event_ref"),
            "error_category": result.get("error_category"),
            "cancel_requested": result.get("cancel_requested", False), "usage": "unknown"}

    async def _result(self):
        if getattr(self, "_dispatch_task", None) is None:
            prepared = self._prepare()
            self._dispatch_task = asyncio.create_task(asyncio.to_thread(self._http, *prepared))
        # A cancelled Langflow request must not imply that the remote agent stopped.
        result = await asyncio.shield(self._dispatch_task)
        self.status = f"Laomedo run {result['run_id']}: {result['status']}"
        return result

    async def run_output(self) -> Data:
        return Data(data=await self._result())

    async def answer_output(self) -> Message:
        result = await self._result()
        return Message(text=result.get("answer") or "")
