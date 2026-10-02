"""OpenCode provider adapter. Production Docker/auth deployment is intentionally gated."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from urllib import request
from urllib.parse import urlencode, urlsplit

from .local_runner import LocalRunner, RunnerError, _copy_tree, _hash_tree, _json

CLI_VERSION = "1.18.33"


class OpenCodeHTTP:
    """Private server protocol, usable for credential-free contract verification.

    A caller must provision a private server with controller/tool isolation before
    exposing real credentials. This adapter never reads or imports personal auth.
    """

    def __init__(self, url, directory, evidence):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"localhost", "127.0.0.1", "::1"} or parsed.username or
                parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise RunnerError("private_opencode_server_required")
        self.url = url.rstrip("/")
        self.directory = directory
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")

    def call(self, method, path, payload=None):
        req = request.Request(self.url + path + "?" + urlencode({"directory": self.directory}),
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method=method)
        with request.urlopen(req, timeout=180) as response:
            value = json.load(response)
        self.log.write(json.dumps({"method": method, "path": path, "response": value}) + "\n")
        self.log.flush()
        return value

    def close(self):
        self.log.close()


def normalize_message(message, skills):
    """Require terminal assistant metadata; normalize observed native tool results."""
    info = message.get("info") or {}
    if info.get("role") != "assistant" or not info.get("time", {}).get("completed"):
        raise RunnerError("opencode_response_not_terminal")
    if info.get("error"):
        raise RunnerError("opencode_provider_error")
    answer, tools = [], []
    for part in message.get("parts", []):
        if part.get("type") == "text":
            answer.append(part.get("text", ""))
        elif part.get("type") == "tool":
            state = part.get("state") or {}
            tools.append({"call_id": part.get("callID"), "tool": part.get("tool"),
                          "status": state.get("status"), "input": state.get("input"),
                          "output": state.get("output"), "error": state.get("error")})
            if state.get("status") in {"pending", "running"}:
                raise RunnerError("opencode_outstanding_tool")
            if part.get("tool") == "skill" and state.get("status") == "completed":
                for skill in skills:
                    if state.get("input", {}).get("name") == skill["skill_id"]:
                        skill["use_evidence"] = "native_skill_tool_completed"
    if not any(answer):
        raise RunnerError("completed_without_agent_message")
    return {"answer": "\n".join(answer), "native_turn_id": info.get("id"),
            "usage": info.get("tokens") if isinstance(info.get("tokens"), dict) else None,
            "tools": tools}


class OpenCodeRunner(LocalRunner):
    """Reuse immutable skills, snapshot lifecycle and bounded dispatch accounting.

    No production transport is installed by default: mounting authentication with
    native OpenCode shell tools would expose it to the model's command execution.
    """

    def __init__(self, *args, transport_factory=None, **kwargs):
        super().__init__(*args, check_docker=False, **kwargs)
        self.transport_factory = transport_factory
        self.active_backends = {}

    def preflight(self):
        return {"provider": "opencode", "cli_version": CLI_VERSION,
                "status": "blocked", "error_category": "opencode_isolated_transport_required",
                "submitted_turns": 0}

    def start(self, request):
        self._validate_provider(request.get("model"), request.get("effort"))
        if self.transport_factory is None:
            raise RunnerError("opencode_isolated_transport_required")
        return super().start(request)

    @staticmethod
    def _validate_provider(model, effort):
        if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.:-]+", model):
            raise RunnerError("opencode_provider_model_required")
        if effort != "default":
            raise RunnerError("unsupported_opencode_effort")

    def _materialize(self, workspace, ref):
        # OpenCode skill names have a narrower grammar than the shared registry.
        if not isinstance(ref, dict) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(ref.get("skill_id", ""))):
            raise RunnerError("unsupported_opencode_skill_name")
        return super()._materialize(workspace, ref)

    def resume(self, run_id, task, *, expected_post_run_hash, expected_thread_id, model, effort):
        self._validate_provider(model, effort)
        record = self.status(run_id)
        if (record.get("provider") != "opencode" or record.get("runtime_version") != CLI_VERSION or
                record["status"] != "completed" or record["thread_id"] != expected_thread_id or
                record["post_run_hash"] != expected_post_run_hash or record["requested_model"] != model or
                record["requested_effort"] != effort or not isinstance(task, str) or not task.strip()):
            raise RunnerError("resume_binding_mismatch")
        root = self._run_dir(run_id)
        if _hash_tree(root / "post-run") != expected_post_run_hash or _hash_tree(root / "workspace") != expected_post_run_hash:
            raise RunnerError("workspace_changed_since_snapshot")
        if (_hash_tree(root / "canonical") != record["source_hash"] or
                (root / "store/sentinel.txt").read_text(encoding="utf-8") != "STORE-ORIGINAL"):
            raise RunnerError("protected_mount_changed")
        return self._execute(run_id, task, resume=True)

    def _execute(self, run_id, task, *, resume):
        if not self.lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        root, record = self._run_dir(run_id), self.status(run_id)
        flag, backend = threading.Event(), None
        self.cancel_flags[run_id] = flag
        record.update(provider="opencode", runtime_version=CLI_VERSION, profile=None,
                      image=None, image_id=None, cli_version="opencode " + CLI_VERSION,
                      config_sha256=None, status="running")
        _json(root / "record.json", record)
        try:
            backend = self.transport_factory(root / "workspace", root)
            self.active_backends[run_id] = backend
            identity = getattr(backend, "runtime_identity", {"provider": "opencode", "runtime_version": CLI_VERSION})
            if resume and record.get("provider_runtime") != identity:
                raise RunnerError("resume_provider_binding_mismatch")
            record["provider_runtime"] = identity
            health = backend.call("GET", "/global/health")
            if health.get("version") != CLI_VERSION or not health.get("healthy"):
                raise RunnerError("opencode_runtime_pin_mismatch")
            provider, model = record["requested_model"].split("/", 1)
            catalog = backend.call("GET", "/provider")
            available = next((item for item in catalog.get("all", []) if item.get("id") == provider), {})
            if provider not in catalog.get("connected", []) or model not in available.get("models", {}):
                raise RunnerError("opencode_model_not_connected")
            self._turn_available()
            if not resume:
                session = backend.call("POST", "/session", {"title": "Laomedo private run"})
                record["thread_id"] = session.get("id")
            if not re.fullmatch(r"ses_[a-zA-Z0-9]+", str(record.get("thread_id", ""))):
                raise RunnerError("opencode_session_identity_invalid")
            record["attempt_number"] = self._reserve_turn()
            _json(root / "record.json", record)
            message = backend.call("POST", "/session/" + record["thread_id"] + "/message",
                {"model": {"providerID": provider, "modelID": model},
                 "parts": [{"type": "text", "text": task}]})
            info = message.get("info") or {}
            if (info.get("sessionID") != record["thread_id"] or
                    info.get("providerID") != provider or info.get("modelID") != model):
                raise RunnerError("opencode_response_identity_mismatch")
            steps = backend.call("GET", "/session/" + record["thread_id"] + "/message")
            observed = dict(message)
            if isinstance(steps, list) and info.get("parentID"):
                observed["parts"] = [part for step in steps
                    if step.get("info", {}).get("role") == "assistant" and
                    step.get("info", {}).get("parentID") == info["parentID"]
                    for part in step.get("parts", []) if part.get("type") == "tool"] + message.get("parts", [])
            normalized = normalize_message(observed, record["skills"])
            record["skill"] = record["skills"][0] if len(record["skills"]) == 1 else None
            if flag.is_set():
                record["status"] = "cancelled"
            else:
                record.update(normalized, status="completed", effective_model=info["providerID"] + "/" + info["modelID"],
                              effective_effort=None)
                pending = root / "post-run-pending"
                post_hash = _copy_tree(root / "workspace", pending)
                old = root / "post-run"
                if old.exists():
                    shutil.rmtree(old)
                pending.rename(old)
                record.update(post_run_hash=post_hash, output_ref=f"laomedo:run:{run_id}:workspace")
            record["turns"].append({"turn_id": normalized["native_turn_id"], "status": record["status"],
                "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest()})
            if (_hash_tree(root / "canonical") != record["source_hash"] or
                    (root / "store/sentinel.txt").read_text(encoding="utf-8") != "STORE-ORIGINAL"):
                raise RunnerError("protected_mount_changed")
        except Exception as exc:
            record.update(status="cancelled" if flag.is_set() else "failed",
                          error_category=str(exc) if isinstance(exc, RunnerError) else type(exc).__name__)
        finally:
            if backend:
                backend.close()
            _json(root / "record.json", record)
            self.cancel_flags.pop(run_id, None)
            self.active_backends.pop(run_id, None)
            self.lock.release()
        return record

    def cancel(self, run_id):
        record = self.status(run_id)
        if record["status"] == "running":
            backend = self.active_backends.get(run_id)
            if backend is None or not record.get("thread_id"):
                raise RunnerError("opencode_cancel_not_dispatchable")
            # Mark cancellation before abort unblocks the message request.
            self.cancel_flags[run_id].set()
            acknowledged = backend.call("POST", "/session/" + record["thread_id"] + "/abort", {})
            if acknowledged is not True:
                raise RunnerError("opencode_abort_not_acknowledged")
            # An acknowledgement is not proof that a native child command terminated.
            return {**record, "cancel_requested": True, "cancel_acknowledged": True,
                    "termination_verified": False}
        return record
