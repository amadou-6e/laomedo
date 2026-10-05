"""Local-only synchronous runner adapter; timeout outcomes are uncertain."""
import json
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

    def dispatch(self, handoff, *, deadline, cancelled, early_start=False, on_ack=None):
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
                task["request_id"] = str(uuid5(UUID(handoff["execution_id"]),
                                               str(handoff["step"])))
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
        if status_code in {400, 401, 403, 404, 422} and isinstance(raw, dict) and not raw.get("run_id"):
            return {"provider": provider, "status": "rejected",
                    "error_category": raw.get("error_category", "runner_rejected")}
        if not isinstance(raw, dict) or not raw.get("run_id"):
            raise HandoffError("invalid_runner_response")
        self.active[handoff["execution_id"]] = (base, raw["run_id"])
        if early_start and provider == "codex" and handoff["operation"] == "fresh":
            if callable(on_ack):
                on_ack({"run_id": raw["run_id"], "status": raw.get("status")})
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
                with urlopen(poll, timeout=max(.001, min(5, deadline - time.monotonic()))) as response:
                    raw = json.load(response)
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
