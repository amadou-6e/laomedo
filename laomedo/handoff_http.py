"""Local-only synchronous runner adapter; timeout outcomes are uncertain."""
import json
import hashlib
import os
import time
from uuid import UUID, uuid5
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit

from .handoffs import HandoffError


class RunnerAdapter:
    def __init__(self, endpoints, token_files=None):
        self.endpoints = dict(endpoints)
        self.token_files = dict(token_files or {})
        self.active = {}
        for base in self.endpoints.values():
            parsed = urlsplit(base)
            if (parsed.scheme != "http" or parsed.hostname not in
                    {"localhost", "127.0.0.1", "::1", "host.docker.internal"} or
                    parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise HandoffError("local_runner_url_required")

    def _headers(self, provider):
        path = self.token_files.get(provider) or os.environ.get(
            "LAOMEDO_" + provider.upper() + "_RUNNER_TOKEN_FILE")
        if not path and provider == "codex":
            path = os.environ.get("LAOMEDO_RUNNER_TOKEN_FILE",
                                  "/run/secrets/laomedo-runner-token")
        if not path:
            raise HandoffError("runner_token_file_required")
        try:
            token = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise HandoffError("runner_token_unavailable") from exc
        if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            raise HandoffError("runner_token_invalid")
        return {"Content-Type": "application/json", "Authorization": "Bearer " + token}

    @staticmethod
    def fresh_request(handoff, request_id):
        """Produce the exact async POST body and runner-compatible digest."""
        if handoff["operation"] != "fresh" or handoff["target"]["provider"] != "codex":
            raise HandoffError("fresh_codex_request_required")
        target = handoff["target"]
        body = {"task": handoff["task"], "model": target["model"],
                "effort": target["effort"], "skill_refs": handoff["skill_refs"],
                "artifact_refs": handoff["artifacts"],
                "handoff": {key: handoff[key] for key in
                            ("execution_id", "step", "source", "workspace_policy")}}
        digest = "sha256:" + hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")).hexdigest()
        return {**body, "request_id": request_id}, digest

    def lookup_request(self, provider, request_id):
        """Authenticated read-only reconciliation, never a second POST."""
        req = Request(self.endpoints[provider] + "/v1/requests/" + request_id,
                      headers=self._headers(provider), method="GET")
        try:
            with urlopen(req, timeout=10) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 409:
                raise HandoffError("runner_request_conflict") from exc
            raise

    def dispatch(self, handoff, *, deadline, cancelled, early_start=False, on_ack=None,
                 runner_request_id=None, expected_request_hash=None):
        if cancelled.is_set() or time.monotonic() >= deadline:
            raise HandoffError("dispatch_stopped")
        target = handoff["target"]
        provider = target["provider"]
        base = self.endpoints[provider]
        headers = self._headers(provider)
        task = {"task": handoff["task"], "model": target["model"], "effort": target["effort"]}
        if handoff["operation"] == "resume":
            prior = handoff["prior"]
            if prior["provider"] != provider:
                raise HandoffError("foreign_resume")
            if prior["model"] != task["model"] or prior["effort"] != task["effort"]:
                raise HandoffError("resume_model_effort_mismatch")
            endpoint = base + "/v1/runs/" + prior["run_id"] + "/resume"
            task.update(expected_post_run_hash=prior["post_run_hash"],
                        expected_thread_id=prior["thread_id"])
            self.active[handoff["execution_id"]] = (base, prior["run_id"])
        else:
            self.active.pop(handoff["execution_id"], None)
            task["skill_refs"] = handoff["skill_refs"]
            task["artifact_refs"] = handoff["artifacts"]
            task["handoff"] = {key: handoff[key] for key in
                               ("execution_id", "step", "source", "workspace_policy")}
            if early_start and provider == "codex":
                request_id = (runner_request_id or
                              str(uuid5(UUID(handoff["execution_id"]),
                                        str(handoff["step"]))))
                task, actual_hash = self.fresh_request(handoff, request_id)
                if (expected_request_hash is not None and
                        actual_hash != expected_request_hash):
                    raise HandoffError("runner_request_changed")
                endpoint = base + "/v1/runs/async"
            else:
                endpoint = base + "/v1/runs"
        request = Request(endpoint, data=json.dumps(task).encode(), method="POST",
                          headers=headers)
        status_code = None
        try:
            with urlopen(request, timeout=max(.001, deadline - time.monotonic())) as response:
                raw = json.load(response)
        except HTTPError as exc:
            status_code = exc.code
            with exc:
                raw = json.load(exc)
        if status_code == 409:
            raise HandoffError("runner_request_conflict")
        if status_code in {400, 401, 403, 404, 422} and isinstance(raw, dict) and not raw.get("run_id"):
            return {"provider": provider, "status": "rejected",
                    "error_category": raw.get("error_category", "runner_rejected")}
        if not isinstance(raw, dict) or not raw.get("run_id"):
            raise HandoffError("invalid_runner_response")
        self.active[handoff["execution_id"]] = (base, raw["run_id"])
        if early_start and provider == "codex" and handoff["operation"] == "fresh":
            if (raw.get("client_request_id") != task["request_id"] or
                    raw.get("raw_event_ref") !=
                    f"laomedo:run:{raw['run_id']}:events"):
                raise HandoffError("runner_ack_identity_mismatch")
            if callable(on_ack):
                on_ack({"run_id": raw["run_id"], "status": raw.get("status"),
                        "client_request_id": raw["client_request_id"],
                        "raw_event_ref": raw["raw_event_ref"]})
            endpoint = base + "/v1/runs/" + raw["run_id"]
            cancel_forwarded = False
            while raw.get("status") in {"prepared", "running"}:
                # Stop may have arrived before the early acknowledgement gave
                # the controller an ID. Forward it once as soon as the ID exists.
                if cancelled.is_set() and not cancel_forwarded:
                    self.cancel(handoff["execution_id"])
                    cancel_forwarded = True
                if time.monotonic() >= deadline:
                    raise HandoffError("runner_result_pending")
                poll = Request(endpoint, headers=headers, method="GET")
                try:
                    with urlopen(poll, timeout=max(.001, min(5, deadline - time.monotonic()))) as response:
                        raw = json.load(response)
                except TimeoutError as exc:
                    if time.monotonic() >= deadline:
                        raise HandoffError("runner_result_pending") from exc
                    raise
                if not isinstance(raw, dict) or raw.get("run_id") != self.active[handoff["execution_id"]][1]:
                    raise HandoffError("runner_poll_identity_mismatch")
                if raw.get("status") in {"prepared", "running"}:
                    time.sleep(min(.05, max(0, deadline - time.monotonic())))
        # Deliberately omit profile, auth, host paths and raw transcript contents.
        return {"provider": provider, "run_id": raw["run_id"], "thread_id": raw.get("thread_id"),
                "status": raw.get("status"), "answer": raw.get("answer"),
                "post_run_hash": raw.get("post_run_hash"), "model": raw.get("requested_model"),
                "effort": raw.get("requested_effort"), "skills": raw.get("skills"),
                "error_category": raw.get("error_category")}

    def status(self, provider, run_id):
        """Read one exact native run without returning its task or transcript."""
        if provider not in self.endpoints or str(UUID(run_id)) != run_id:
            raise HandoffError("invalid_runner_status_identity")
        req = Request(self.endpoints[provider] + "/v1/runs/" + run_id,
                      headers=self._headers(provider), method="GET")
        with urlopen(req, timeout=10) as response:
            value = json.load(response)
        if not isinstance(value, dict) or value.get("run_id") != run_id:
            raise HandoffError("runner_status_identity_mismatch")
        return {key: value.get(key) for key in
                ("run_id", "status", "cancel_requested", "cancel_confirmed")}

    def cancel(self, execution_id):
        active = self.active.get(execution_id)
        if active is None:
            # Fresh runner POST does not publish run ID before completing (#22).
            return {"cancel_acknowledged": False, "reason": "active_run_id_unavailable"}
        base, run_id = active
        provider = next(p for p, url in self.endpoints.items() if url == base)
        req = Request(base + "/v1/runs/" + run_id + "/cancel", data=b"{}", method="POST",
                      headers=self._headers(provider))
        with urlopen(req, timeout=10) as response:
            return json.load(response)

    def select_artifacts(self, source, paths):
        if source is None or not paths:
            return []
        endpoint = self.endpoints[source["provider"]] + "/v1/runs/" + source["run_id"] + "/artifacts"
        req = Request(endpoint, data=json.dumps({"paths": paths}).encode(), method="POST",
                      headers=self._headers(source["provider"]))
        with urlopen(req, timeout=10) as response:
            result = json.load(response)
        return result["artifact_refs"]
