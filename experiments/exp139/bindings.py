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

from laomedo.local_runner import AppServer, LocalRunner, RunnerError


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
GIT_OVERRIDE = ('permissions={container-edit={filesystem={":root"="read",'
    '":workspace_roots"="write","/home/runner/.codex/auth.json"="deny",'
    '"/draft/.git"="write"},network={enabled=false}}}')
PROFILE_OVERRIDES = ["-c", 'default_permissions="container-edit"',
                     "-c", 'approval_policy="never"', "-c", GIT_OVERRIDE]


class GitMetadataAppServer(AppServer):
    """Invocation-only approved rule; original config and auth denial remain."""
    def __init__(self, command, evidence, **kwargs):
        if command[-2:] != ["app-server", "--stdio"]:
            raise RunnerError("experiment_app_server_invocation_changed")
        redactions = list(kwargs.pop("secret_redactions", ()))
        for position, value in enumerate(command[:-1]):
            if value == "--mount":
                mount = dict(item.split("=", 1) for item in command[position + 1].split(",") if "=" in item)
                if mount.get("target") == "/run/laomedo/capability":
                    redactions.append(Path(mount["source"]).read_text().strip())
        super().__init__([*command[:-2], *PROFILE_OVERRIDES, *command[-2:]], evidence,
                         secret_redactions=tuple(redactions), **kwargs)


class MailboxAppServer(GitMetadataAppServer):
    """Prospective invocation-only relay; not activated by importing this module."""
    def __init__(self, command, evidence, **kwargs):
        command = list(command)
        client = Path(__file__).with_name("mailbox_client.mjs")
        relay = client.with_name("mailbox_relay.mjs")
        client_index = next((index for index, item in enumerate(command)
            if item == "--mount" and "target=/run/laomedo/mediate.mjs," in command[index + 1]), None)
        if client_index is not None:
            # Replace only the trusted client mount; the graph never chooses it.
            command[client_index + 1] = f"type=bind,source={client},target=/run/laomedo/mediate.mjs,readonly"
            bootstrap = command.index("bootstrap")
            image_index = command.index("--workdir") + 2
            command[image_index:image_index] = ["--mount",
                f"type=bind,source={relay},target=/run/laomedo/relay.mjs,readonly",
                "--env", "GIT_EXEC_PATH=/run/laomedo/bin"]
            bootstrap = command.index("bootstrap")
            command[bootstrap - 1] = (
                'cp /config.toml /home/runner/.codex/config.toml && '
                'node /run/laomedo/relay.mjs & relay=$!; '
                'for n in $(seq 1 100); do '
                'test -f /draft/.git/laomedo-mediation/ready && break; '
                'kill -0 "$relay" 2>/dev/null || exit 2; sleep 0.05; done; '
                'test -f /draft/.git/laomedo-mediation/ready || exit 2; '
                'exec codex "$@"')
        super().__init__(command, evidence, **kwargs)
