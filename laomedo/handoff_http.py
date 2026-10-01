"""Local-only synchronous runner adapter; timeout outcomes are uncertain."""
import json
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from .handoffs import HandoffError


class RunnerAdapter:
    def __init__(self, endpoints):
        self.endpoints = dict(endpoints)
        self.active = {}
        for base in self.endpoints.values():
            parsed = urlsplit(base)
            if (parsed.scheme != "http" or parsed.hostname not in
                    {"localhost", "127.0.0.1", "::1", "host.docker.internal"} or
                    parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise HandoffError("local_runner_url_required")

    def dispatch(self, handoff, *, deadline, cancelled):
        if cancelled.is_set() or time.monotonic() >= deadline:
            raise HandoffError("dispatch_stopped")
        target = handoff["target"]
        provider = target["provider"]
        base = self.endpoints[provider]
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
            task["skill_refs"] = handoff["skill_refs"]
            endpoint = base + "/v1/runs"
        request = Request(endpoint, data=json.dumps(task).encode(), method="POST",
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=max(.001, deadline - time.monotonic())) as response:
            raw = json.load(response)
        if not isinstance(raw, dict) or not raw.get("run_id"):
            raise HandoffError("invalid_runner_response")
        self.active[handoff["execution_id"]] = (base, raw["run_id"])
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
        req = Request(base + "/v1/runs/" + run_id + "/cancel", data=b"{}", method="POST",
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as response:
            return json.load(response)
