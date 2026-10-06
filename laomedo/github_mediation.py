"""Run-scoped mediated GitHub effects; credential transport stays outside agents.

This module owns durable authorization and uncertain-write semantics. It does
not supply a GitHub credential, a literal gh/git adapter, or a service lifetime.
The transport is injected by the credential-owning process, never by a stage.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Callable


READS = frozenset({"git_fetch", "pr_list", "issue_list", "actions_read", "api_rest_read"})
WRITES = frozenset({"git_push", "pr_create", "pr_update", "issue_create", "api_rest_write", "api_graphql_mutation"})
OPERATIONS = READS | WRITES


class MediationError(Exception):
    """Typed refusal; `code` is safe for a stage or trace."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class KnownRejected(Exception):
    """Transport-confirmed rejection which did not create a remote effect."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _request_hash(repository: str, operation: str, payload: dict) -> str:
    try:
        encoded = json.dumps({"repository": repository, "operation": operation,
                              "payload": payload}, sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MediationError("request_not_serializable") from error
    if len(encoded) > 1024 * 1024:
        raise MediationError("request_too_large")
    return sha256(encoded).hexdigest()


def _target_key(repository: str, operation: str, payload: dict) -> str:
    if operation == "pr_create":
        target = ["pr", repository, payload["head"], payload["base"]]
    elif operation == "pr_update":
        target = ["pr_update", repository, payload["number"]]
    elif operation == "issue_create":
        target = ["issue", repository, payload["reviewed_proposal_id"]]
    elif operation == "git_push":
        target = ["push", repository, payload["branch"]]
    else:
        target = [operation, repository]
    return json.dumps(target, separators=(",", ":"))


def _validate_effect(operation: str, payload: dict, grant, db,
                     workflow_change_classifier) -> None:
    """Enforce semantic approval before a generic API mutation is dispatched."""
    if operation == "git_push":
        if not all(isinstance(payload.get(key), str) and payload[key]
                   for key in ("branch", "commit")):
            raise MediationError("push_identity_required")
        if payload["branch"].startswith("refs/") or ".." in payload["branch"]:
            raise MediationError("push_branch_invalid")
        if payload["branch"] != grant["branch"]:
            raise MediationError("push_branch_denied")
        # Only a trusted inspection of the actual outgoing diff may decide
        # whether the separate workflow-file approval is needed.
        if workflow_change_classifier is None:
            raise MediationError("push_diff_unverified")
        try:
            changes_workflow = workflow_change_classifier(
                grant["repository"], payload["branch"], payload["commit"])
        except Exception:
            raise MediationError("push_diff_unverified") from None
        if changes_workflow is not False:
            raise MediationError("workflow_approval_required" if changes_workflow is True
                                 else "push_diff_unverified")
    if operation in {"pr_create", "pr_update"}:
        if not all(isinstance(payload.get(key), str) and payload[key]
                   for key in ("head", "base", "marker")):
            raise MediationError("pr_identity_required")
        if operation == "pr_update":
            if type(payload.get("number")) is not int or payload["number"] < 1:
                raise MediationError("target_pr_required")
            target = db.execute("SELECT base FROM pr_targets WHERE grant_id=? AND number=?",
                                (grant["grant_id"], payload["number"])).fetchone()
            if (target is None or payload["head"] != grant["branch"] or
                    payload["base"] != target["base"]):
                raise MediationError("target_pr_denied")
        if operation == "pr_create" and payload["head"] != grant["branch"]:
            raise MediationError("pr_head_denied")
    if operation == "issue_create":
        if not all(isinstance(payload.get(key), str) and payload[key]
                   for key in ("reviewed_proposal_id", "marker")):
            raise MediationError("reviewed_issue_required")
        reviewed = json.loads(grant["reviewed_issue_hashes"])
        if reviewed.get(payload["reviewed_proposal_id"]) != _request_hash(
                grant["repository"], "issue_create", payload):
            raise MediationError("issue_review_denied")
    if operation in {"api_rest_write", "api_graphql_mutation"}:
        # An agent-declared semantic_operation is not a security classifier.
        # The real endpoint/query parser must be reviewed before this lane opens.
        raise MediationError("api_write_unsupported")


def _validate_read(operation: str, payload: dict, repository: str) -> None:
    if operation != "api_rest_read":
        return
    path = payload.get("path")
    prefix = f"/repos/{repository}/"
    if (payload.get("method", "GET") != "GET" or not isinstance(path, str) or
            not path.startswith(prefix) or
            any(part in path for part in ("..", "//", "\\", "%", "?", "#"))):
        raise MediationError("api_read_denied")


class MediationStore:
    """Durable grant/effect ledger for one trusted mediator process family."""

    def __init__(self, path: str | Path, *, now: Callable[[], float] = time.time,
                 workflow_change_classifier=None):
        candidate = Path(path).expanduser()
        if not candidate.is_absolute() or candidate.is_symlink():
            raise MediationError("store_path_invalid")
        self.path = candidate.resolve()
        if any((parent / ".git").exists() for parent in
               (self.path.parent, *self.path.parent.parents)):
            raise MediationError("store_inside_checkout")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.now = now
        self.workflow_change_classifier = workflow_change_classifier
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS grants (
                    token_hash TEXT PRIMARY KEY, grant_id TEXT UNIQUE NOT NULL,
                    run_id TEXT NOT NULL, invocation_id TEXT NOT NULL,
                    repository TEXT NOT NULL, operations TEXT NOT NULL,
                    branch TEXT, reviewed_issue_hashes TEXT NOT NULL,
                    expires_at REAL NOT NULL, revoked_at REAL);
                CREATE TABLE IF NOT EXISTS effects (
                    run_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL, repository TEXT NOT NULL,
                    operation TEXT NOT NULL, target_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_json TEXT, error_code TEXT,
                    PRIMARY KEY(run_id,effect_id));
                CREATE TABLE IF NOT EXISTS retry_approvals (
                    prior_run_id TEXT NOT NULL, prior_effect_id TEXT NOT NULL,
                    next_run_id TEXT NOT NULL, next_effect_id TEXT NOT NULL,
                    approved_by TEXT NOT NULL, used_at REAL,
                    PRIMARY KEY(next_run_id,next_effect_id));
                CREATE TABLE IF NOT EXISTS lease_bindings (
                    grant_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    lease_token TEXT UNIQUE NOT NULL, lease_scope TEXT NOT NULL,
                    service_instance TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pr_targets (
                    grant_id TEXT NOT NULL, number INTEGER NOT NULL,
                    base TEXT NOT NULL, PRIMARY KEY(grant_id,number));
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def issue(self, *, run_id: str, invocation_id: str, repository: str,
              operations: set[str], ttl_seconds: float, branch: str | None = None,
              reviewed_issue_requests: dict[str, dict] | None = None,
              lease_token: str | None = None, lease_scope: str | None = None,
              service_instance: str | None = None,
              target_prs: dict[int, str] | None = None) -> tuple[str, str]:
        reviewed_issue_requests = reviewed_issue_requests or {}
        target_prs = target_prs or {}
        if (not all(isinstance(v, str) and v for v in (run_id, invocation_id, repository)) or
                not isinstance(operations, set) or not operations or
                not operations <= OPERATIONS or not 0 < ttl_seconds <= 60 or
                (operations & {"git_push", "pr_create"} and not branch) or
                (branch is not None and (not isinstance(branch, str) or not branch)) or
                not isinstance(reviewed_issue_requests, dict) or
                any(not isinstance(k, str) or not k or not isinstance(v, dict) or
                    v.get("reviewed_proposal_id") != k for k, v in
                    reviewed_issue_requests.items()) or
                ("issue_create" in operations and not reviewed_issue_requests) or
                (any(v is not None for v in (lease_token, lease_scope, service_instance)) and
                 not all(isinstance(v, str) and v for v in
                         (lease_token, lease_scope, service_instance))) or
                not isinstance(target_prs, dict) or
                any(type(number) is not int or number < 1 or
                    not isinstance(base, str) or not base
                    for number, base in target_prs.items())):
            raise MediationError("grant_request_invalid")
        reviewed_hashes = {key: _request_hash(repository, "issue_create", body)
                           for key, body in reviewed_issue_requests.items()}
        grant_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO grants VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                       (sha256(token.encode()).hexdigest(), grant_id, run_id,
                        invocation_id, repository, json.dumps(sorted(operations)), branch,
                        json.dumps(reviewed_hashes, sort_keys=True),
                        self.now() + ttl_seconds))
            if lease_token is not None:
                db.execute("INSERT INTO lease_bindings VALUES (?,?,?,?,?)",
                           (grant_id, run_id, lease_token, lease_scope, service_instance))
            for number, base in target_prs.items():
                db.execute("INSERT INTO pr_targets VALUES (?,?,?)",
                           (grant_id, number, base))
        return grant_id, token

    def revoke_lease(self, *, run_id: str, lease_token: str,
                     lease_scope: str) -> list[str]:
        """Trusted lease service revokes only the exact persisted binding."""
        with closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT grant_id FROM lease_bindings WHERE run_id=? AND lease_token=? AND lease_scope=?",
                (run_id, lease_token, lease_scope)).fetchall()
            ids = [row["grant_id"] for row in rows]
            for grant_id in ids:
                db.execute("UPDATE grants SET revoked_at=? WHERE grant_id=? AND revoked_at IS NULL",
                           (self.now(), grant_id))
            return ids

    def renew_lease(self, *, run_id: str, lease_token: str,
                    lease_scope: str, ttl_seconds: float) -> bool:
        if not 0 < ttl_seconds <= 60:
            raise MediationError("grant_renewal_invalid")
        with closing(self._connect()) as db, db:
            result = db.execute(
                "UPDATE grants SET expires_at=? WHERE grant_id IN "
                "(SELECT grant_id FROM lease_bindings WHERE run_id=? AND lease_token=? AND lease_scope=?) "
                "AND revoked_at IS NULL AND expires_at>?",
                (self.now() + ttl_seconds, run_id, lease_token, lease_scope, self.now()))
            return result.rowcount == 1

    def revoke_lease_scope(self, lease_scope: str) -> int:
        """Fail closed on service startup; previous instance grants never survive."""
        with closing(self._connect()) as db, db:
            result = db.execute(
                "UPDATE grants SET revoked_at=? WHERE grant_id IN "
                "(SELECT grant_id FROM lease_bindings WHERE lease_scope=?) AND revoked_at IS NULL",
                (self.now(), lease_scope))
            return result.rowcount

    def revoke_run(self, run_id: str) -> int:
        """A lease owner can revoke all of a run's grants without its token."""
        with closing(self._connect()) as db, db:
            result = db.execute("UPDATE grants SET revoked_at=? WHERE run_id=? AND revoked_at IS NULL",
                                (self.now(), run_id))
            return result.rowcount

    def renew_grant(self, grant_id: str, ttl_seconds: float) -> bool:
        """Trusted lease owner extends a live grant; never resurrects one."""
        if not isinstance(grant_id, str) or not grant_id or not 0 < ttl_seconds <= 60:
            raise MediationError("grant_renewal_invalid")
        with closing(self._connect()) as db, db:
            result = db.execute(
                "UPDATE grants SET expires_at=? WHERE grant_id=? AND revoked_at IS NULL "
                "AND expires_at>?",
                (self.now() + ttl_seconds, grant_id, self.now()))
            return result.rowcount == 1

    def authorize_new_attempt(self, *, prior_run_id: str, prior_effect_id: str,
                              next_run_id: str, next_effect_id: str,
                              approved_by: str) -> None:
        """Trusted controller records explicit user consent to duplicate risk.

        This method must never be exposed to an agent's run capability.
        """
        if not all(isinstance(value, str) and value for value in
                   (prior_run_id, prior_effect_id, next_run_id, next_effect_id, approved_by)):
            raise MediationError("retry_approval_invalid")
        with closing(self._connect()) as db, db:
            prior = db.execute("SELECT state FROM effects WHERE run_id=? AND effect_id=?",
                               (prior_run_id, prior_effect_id)).fetchone()
            if prior is None or prior["state"] != "unknown":
                raise MediationError("prior_effect_not_unknown")
            db.execute("INSERT INTO retry_approvals VALUES (?,?,?,?,?,NULL)",
                       (prior_run_id, prior_effect_id, next_run_id,
                        next_effect_id, approved_by))

    def _grant(self, db, token: str, repository: str, operation: str):
        if not isinstance(token, str) or not token:
            raise MediationError("grant_unavailable")
        row = db.execute("SELECT * FROM grants WHERE token_hash=?",
                         (sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None or row["revoked_at"] is not None or row["expires_at"] <= self.now():
            raise MediationError("grant_unavailable")
        if row["repository"] != repository:
            raise MediationError("repository_denied")
        if operation not in json.loads(row["operations"]):
            raise MediationError("operation_denied")
        return row

    def invoke(self, *, token: str, repository: str, operation: str,
               payload: dict, effect_id: str | None,
               transport: Callable[[str, str, dict], dict]) -> dict:
        if operation not in OPERATIONS:
            raise MediationError("unsupported_operation")
        if not isinstance(payload, dict):
            raise MediationError("request_invalid")
        # Freeze caller-owned data before hashing and forwarding it. A stage
        # cannot mutate a nested dict between the journal and transport call.
        try:
            payload = json.loads(json.dumps(payload, ensure_ascii=False,
                                            allow_nan=False))
        except (TypeError, ValueError) as error:
            raise MediationError("request_not_serializable") from error
        if operation in WRITES:
            if not isinstance(effect_id, str) or not 0 < len(effect_id) <= 128:
                raise MediationError("effect_id_required")
        digest = _request_hash(repository, operation, payload)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            grant = self._grant(db, token, repository, operation)
            if operation in READS:
                _validate_read(operation, payload, repository)
            if operation in WRITES:
                _validate_effect(operation, payload, grant, db,
                                 self.workflow_change_classifier)
                prior = db.execute("SELECT * FROM effects WHERE run_id=? AND effect_id=?",
                                   (grant["run_id"], effect_id)).fetchone()
                if prior:
                    if prior["request_hash"] != digest:
                        raise MediationError("effect_conflict")
                    if prior["state"] == "confirmed":
                        return {"state": "confirmed", "resent": False,
                                "result": json.loads(prior["result_json"])}
                    if prior["state"] == "rejected":
                        return {"state": "rejected", "resent": False,
                                "error": prior["error_code"]}
                    return {"state": "unknown", "resent": False}
                target_key = _target_key(repository, operation, payload)
                prior_target = db.execute(
                    "SELECT run_id,effect_id FROM effects WHERE target_key=? "
                    "AND state='unknown' ORDER BY rowid DESC LIMIT 1",
                    (target_key,)).fetchone()
                if prior_target is None and operation in {"pr_create", "issue_create"} and db.execute(
                        "SELECT 1 FROM effects WHERE target_key=? AND state='confirmed' LIMIT 1",
                        (target_key,)).fetchone():
                    raise MediationError("target_already_confirmed")
                if prior_target:
                    approval = db.execute(
                        "SELECT approved_by FROM retry_approvals WHERE prior_run_id=? "
                        "AND prior_effect_id=? AND next_run_id=? AND next_effect_id=? "
                        "AND used_at IS NULL",
                        (prior_target["run_id"], prior_target["effect_id"],
                         grant["run_id"], effect_id)).fetchone()
                    if approval is None:
                        raise MediationError("prior_effect_unknown")
                    db.execute("UPDATE retry_approvals SET used_at=? WHERE next_run_id=? "
                               "AND next_effect_id=? AND used_at IS NULL",
                               (self.now(), grant["run_id"], effect_id))
                db.execute("INSERT INTO effects VALUES (?,?,?,?,?,?,'unknown',NULL,NULL)",
                           (grant["run_id"], effect_id, digest, repository,
                            operation, target_key))
        # The intent is committed before entering the untrusted remote call.
        # After any ambiguous failure, an exact repeat returns unknown.
        try:
            result = transport(repository, operation, payload)
            if not isinstance(result, dict):
                raise ValueError("transport_result_invalid")
        except KnownRejected as error:
            state, result, error_code = "rejected", None, error.code
        except Exception:
            return {"state": "unknown", "resent": False}
        else:
            state, error_code = "confirmed", None
        if operation in READS:
            if state == "rejected":
                return {"state": "rejected", "error": error_code}
            return {"state": "confirmed", "result": result}
        with closing(self._connect()) as db, db:
            if state == "confirmed" and operation == "pr_create" and \
                    type(result.get("number")) is int and result["number"] > 0:
                db.execute("INSERT OR IGNORE INTO pr_targets VALUES (?,?,?)",
                           (grant["grant_id"], result["number"], payload["base"]))
            db.execute("UPDATE effects SET state=?,result_json=?,error_code=? "
                       "WHERE run_id=? AND effect_id=? AND state='unknown'",
                       (state, json.dumps(result) if result is not None else None,
                        error_code, grant["run_id"], effect_id))
        return ({"state": "confirmed", "result": result} if state == "confirmed"
                else {"state": "rejected", "error": error_code})

    def effect(self, run_id: str, effect_id: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT state,result_json,error_code FROM effects "
                             "WHERE run_id=? AND effect_id=?", (run_id, effect_id)).fetchone()
        return dict(row) if row else None
