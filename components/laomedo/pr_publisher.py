"""Request the trusted host publisher after accepted-success graph routing."""

import json
import os
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
from uuid import UUID

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, IntInput, Output, StrInput
from lfx.schema import Data


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class LaomedoPRPublisher(Component):
    display_name = "Laomedo Draft PR Publisher"
    description = "Request draft publication through the controller-owned trusted handoff. No GitHub credential or grant enters the graph."
    name = "LaomedoPRPublisher"
    icon = "GitPullRequest"
    inputs = [DataInput(name="validation", display_name="Accepted Output", required=True),
              StrInput(name="runner_url", display_name="Runner URL", value="http://host.docker.internal:8765", advanced=True),
              IntInput(name="timeout_seconds", display_name="HTTP Timeout", value=30, advanced=True)]
    outputs = [Output(name="publication", display_name="Publication Outcome", method="publication_output")]

    def publication_output(self) -> Data:
        validation = self.validation.data
        envelope = validation.get("agent_submission", {})
        if (validation.get("contract_status") != "accepted" or
                envelope.get("task_outcome") != "success" or
                envelope.get("executor_status") != "completed" or
                envelope.get("evidence_complete") is not True):
            return Data(data={"phase": "rejected", "publication_state": "not_dispatched"})
        # This is only a convenience check. The host recomputes validation
        # from its own frozen data; a forged accepted result cannot authorize.
        reference = envelope.get("run_reference", {})
        run_id = reference.get("run_id")
        if not isinstance(run_id, str) or str(UUID(run_id)) != run_id:
            raise ValueError("publication_run_id_required")
        base = str(self.runner_url).rstrip("/")
        url = urlsplit(base)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
                or url.username or url.password or url.path or url.query or url.fragment):
            raise ValueError("local_runner_url_required")
        timeout = self.timeout_seconds
        if type(timeout) is not int or not 1 <= timeout <= 300:
            raise ValueError("publication_timeout_invalid")
        try:
            token = Path(os.environ.get("LAOMEDO_RUNNER_TOKEN_FILE", "/run/secrets/laomedo-runner-token")).read_text(encoding="utf-8").strip()
            if not token:
                raise ValueError("missing_runner_token")
            req = request.Request(base + "/v1/runs/" + run_id + "/publish", data=b"{}",
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")
            # No automatic resend, including redirects. Lost acknowledgement
            # is unknown even if a draft PR was successfully created.
            with request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
                result = json.load(response)
            if result.get("run_id") != run_id:
                raise ValueError("publication_identity_mismatch")
            handoff = result["publication_handoff"]
            phase = handoff["phase"]
            state = handoff.get("publication", {}).get("state", "not_dispatched")
            if phase not in {"completed", "rejected", "failed", "unknown", "expired", "cancelled"}:
                raise ValueError("publication_phase_invalid")
            if state not in {"confirmed", "rejected", "unknown", "not_dispatched"}:
                raise ValueError("publication_state_invalid")
            return Data(data={"run_id": run_id, "phase": phase, "publication_state": state})
        except Exception:
            # A transport exception may follow a POST. Never call it safely
            # failed or leak provider text/token paths into the graph.
            return Data(data={"run_id": run_id, "phase": "unknown", "publication_state": "unknown"})
