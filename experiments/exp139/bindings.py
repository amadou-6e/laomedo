"""Explicit host-only graph dispatch binding for this disposable experiment.

Not a production authorization service. Grants still only scope runs; a process
under the same OS user can change host state. No graph supplies an authorization.
"""
from copy import deepcopy
import hashlib
import json
import threading

from laomedo.local_runner import LocalRunner, RunnerError


def request_digest(request):
    body = {key: value for key, value in request.items() if key != "request_id"}
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class BoundRunner(LocalRunner):
    def __init__(self, *args, approved_requests, authorization_factory, **kwargs):
        self.approved_requests = dict(approved_requests)
        self.authorization_factory = authorization_factory
        self.binding_lock = threading.Lock()
        self.consumed_bindings = set()
        super().__init__(*args, **kwargs)

    def _prepare(self, request, **kwargs):
        if not isinstance(request, dict) or "github_authorization_ref" in request:
            raise RunnerError("experiment_request_binding_denied")
        digest = request_digest(request)
        with self.binding_lock:
            if digest not in self.approved_requests or digest in self.consumed_bindings:
                raise RunnerError("experiment_request_binding_denied")
            # Consume before preparing. Failed preparations never retry a grant
            # implicitly; amendment/review is required for another dispatch.
            self.consumed_bindings.add(digest)
        selected = deepcopy(request)
        case = self.approved_requests[digest]
        if case == "success":
            selected["github_authorization_ref"] = self.authorization_factory()
        # Preserve the original graph request hash for Stop/reconciliation.
        return super()._prepare(selected, **kwargs)
