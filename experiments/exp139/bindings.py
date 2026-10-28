"""Explicit host-only graph dispatch binding for this disposable experiment.

Not a production authorization service. Grants still only scope runs; a process
under the same OS user can change host state. No graph supplies an authorization.
"""
from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

from laomedo.agents.providers.codex.native.server import AppServer; from laomedo.agents.providers.codex.runner import CodexRunner as LocalRunner; from laomedo.agents.runtime.errors import RunnerError


def request_digest(request):
    body = {key: value for key, value in request.items() if key != "request_id"}
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class BoundRunner(LocalRunner):
    def __init__(self, *args, approved_requests, authorization_factory,
                 nonpublishing_lease_service=None, binding_state=None,
                 seed_consumed=(), **kwargs):
        self.approved_requests = dict(approved_requests)
        self.authorization_factory = authorization_factory
        self.binding_lock = threading.Lock()
        self.consumed_bindings = set()
        self.binding_state = binding_state
        self.execution_cases = {}
        self.dispatch_lock = threading.Lock()
        self.nonpublishing_lease_service = nonpublishing_lease_service
        if binding_state is not None:
            with closing(sqlite3.connect(binding_state)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS consumed (digest TEXT PRIMARY KEY)")
                db.executemany("INSERT OR IGNORE INTO consumed VALUES (?)", ((item,) for item in seed_consumed))
        super().__init__(*args, **kwargs)

    def resume(self, *args, **kwargs):
        raise RunnerError("experiment_resume_denied")

    def _execute(self, run_id, task, *, resume):
        if resume or run_id not in self.execution_cases:
            raise RunnerError("experiment_resume_denied")
        if not self.dispatch_lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        mediated = self.lease_service
        try:
            case = self.execution_cases[run_id]
            has_scope = self.status(run_id).get("github_scope") is not None
            if has_scope != (case == "success"):
                raise RunnerError("experiment_supervisor_scope_mismatch")
            if case != "success":
                if self.nonpublishing_lease_service is None:
                    raise RunnerError("experiment_nonpublishing_supervisor_required")
                self.lease_service = self.nonpublishing_lease_service
            return super()._execute(run_id, task, resume=False)
        finally:
            self.lease_service = mediated
            self.dispatch_lock.release()

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
            if self.binding_state is not None:
                with closing(sqlite3.connect(self.binding_state)) as db, db:
                    try:
                        db.execute("INSERT INTO consumed VALUES (?)", (digest,))
                    except sqlite3.IntegrityError:
                        raise RunnerError("experiment_request_binding_denied") from None
        selected = deepcopy(request)
        case = self.approved_requests[digest]
        if case == "success":
            selected["github_authorization_ref"] = self.authorization_factory()
        # Preserve the original graph request hash for Stop/reconciliation.
        record = super()._prepare(selected, **kwargs)
        if record.get("run_id"):
            self.execution_cases[record["run_id"]] = case
        return record


# The CLI's dotted-key override parser splits the literal `.git` path, and a
# partial permissions table loses the default profile. Supply the complete
# original policy plus the sole approved Git-metadata rule as an inline table.


class GitMetadataAppServer(AppServer):
    """Apply the same approved invocation rule to a typed SDK launch."""

    def __init__(self, launch, evidence, **kwargs):
        """Preserve run-capability redaction while forwarding native transport limits."""
        from experiments.exp139.models import GitMetadataLaunch
        redactions = list(kwargs.pop("secret_redactions", ()))
        if launch.capability is not None:
            value = launch.capability.read_text().strip()
            if value not in redactions:
                redactions.append(value)
        super().__init__(GitMetadataLaunch.from_launch(launch), evidence,
                         secret_redactions=tuple(redactions), **kwargs)



class MailboxAppServer(GitMetadataAppServer):
    """Prospective SDK relay policy; importing it never activates a connection."""

    def __init__(self, launch, evidence, **kwargs):
        """Select only host-owned relay files and preserve the canonical launch."""
        from experiments.exp139.models import MailboxLaunch
        super().__init__(MailboxLaunch.from_launch(launch), evidence, **kwargs)
