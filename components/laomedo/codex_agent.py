"""Langflow 1.12.3 custom component for the private local Codex runner."""

import asyncio
import json
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
        DataInput(name="skill_reference", display_name="Skill References", is_list=True),
        StrInput(name="skill_id", display_name="Skill ID", advanced=True),
        StrInput(name="revision_id", display_name="Skill Revision", advanced=True),
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
            connected = getattr(self, "skill_reference", None)
            if connected in (None, "", []):
                connected = None
            if connected is not None:
                refs = connected if isinstance(connected, list) else [connected]
                refs = [getattr(ref, "data", ref) for ref in refs]
                if not 1 <= len(refs) <= 16:
                    raise ValueError("one_to_sixteen_skills_required")
                seen = set()
                for ref in refs:
                    if (not isinstance(ref, dict) or
                            not isinstance(ref.get("skill_id"), str) or
                            not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", ref["skill_id"]) or
                            not isinstance(ref.get("revision_id"), str) or
                            not re.fullmatch(r"sha256:[0-9a-f]{64}", ref["revision_id"]) or
                            ref.get("tree_hash") != ref["revision_id"]):
                        raise ValueError("invalid_skill_reference")
                    if ref["skill_id"] in seen:
                        raise ValueError("duplicate_skill_id")
                    seen.add(ref["skill_id"])
                if len(refs) > 1:
                    if getattr(self, "skill_id", "") or getattr(self, "revision_id", ""):
                        raise ValueError("conflicting_skill_inputs")
                    return base + "/v1/runs", {"task": task, "model": model,
                        "effort": effort, "skill_refs": refs}, "POST"
                connected = refs[0]
            revision = str(getattr(self, "revision_id", "") or "")
            skill_id = str(getattr(self, "skill_id", "") or "")
            if connected is not None:
                if not isinstance(connected, dict):
                    raise ValueError("invalid_skill_reference")
                selected_id = connected.get("skill_id")
                selected_revision = connected.get("revision_id")
                if (not isinstance(selected_id, str) or
                        not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", selected_id) or
                        not isinstance(selected_revision, str) or
                        not re.fullmatch(r"sha256:[0-9a-f]{64}", selected_revision) or
                        connected.get("tree_hash") != selected_revision):
                    raise ValueError("invalid_skill_reference")
                if (skill_id and skill_id != selected_id) or (revision and revision != selected_revision):
                    raise ValueError("conflicting_skill_inputs")
                skill_id, revision = selected_id, selected_revision
            if not skill_id.strip() or not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
                raise ValueError("pinned_skill_required")
            return base + "/v1/runs", {"task": task, "model": model, "effort": effort,
                "skill_ref": {"skill_id": skill_id,
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
        req = request.Request(endpoint,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method=method)
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
        skills = result.get("skills") or ([skill] if skill else [])
        return {"answer": result.get("answer"), "run_id": result["run_id"],
            "provider": result.get("provider", "codex"),
            "thread_id": result.get("thread_id"), "status": result.get("status"),
            "post_run_hash": result.get("post_run_hash"),
            "model": result.get("requested_model"), "effort": result.get("requested_effort"),
            "skill_revision": skill.get("revision_id"),
            "skill_use_evidence": skill.get("use_evidence", "unknown"),
            "skills": skills,
            "artifact_ref": result.get("output_ref"), "trace_ref": result.get("raw_event_ref"),
            "error_category": result.get("error_category"),
            "cancel_requested": result.get("cancel_requested", False),
            "usage": result.get("usage") if isinstance(result.get("usage"), dict) else "unknown"}

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
