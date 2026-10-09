"""Trusted, durable run approval consumed by the independent lease service.

Only the user-facing controller may call ``approve`` and ``bind_run``. Neither
method is exposed through the agent's mediator capability. The lease service
uses ``authorize_lease`` to compare runner-supplied claims with this record.
This local prototype still needs an OS/service identity boundary before
multi-user or production use.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3

from .github_mediation import MediationError


FIRST_SLICE_OPERATIONS = frozenset({"git_push", "pr_create", "pr_update", "pr_read", "actions_read"})


class RunGrantAuthority:
    def __init__(self, path: str | Path, *, connection_authorizer=None,
                 diagnostic_repository_read: bool = False):
        # Same-repository REST read is a D2 diagnostic control, not part of
        # the accepted first-slice grant. Production callers leave this off.
        candidate = Path(path).expanduser()
        if not candidate.is_absolute() or candidate.is_symlink():
            raise MediationError("authority_path_invalid")
        self.path = candidate.resolve()
        if any((parent / ".git").exists() for parent in
               (self.path.parent, *self.path.parent.parents)):
            raise MediationError("authority_inside_checkout")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection_authorizer = connection_authorizer
        self.diagnostic_repository_read = diagnostic_repository_read is True
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS authorizations (
                ref_hash TEXT PRIMARY KEY, run_id TEXT UNIQUE,
                invocation_id TEXT NOT NULL, repository TEXT NOT NULL,
                branch TEXT NOT NULL, operations TEXT NOT NULL,
                reviewed_by TEXT NOT NULL, lease_token TEXT UNIQUE,
                target_prs TEXT NOT NULL DEFAULT '{}',
                connection_id TEXT, connection_generation INTEGER)""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(authorizations)")}
            if "target_prs" not in columns:
                db.execute("ALTER TABLE authorizations ADD COLUMN target_prs TEXT NOT NULL "
                           "DEFAULT '{}'")
            if "connection_id" not in columns:
                db.execute("ALTER TABLE authorizations ADD COLUMN connection_id TEXT")
            if "connection_generation" not in columns:
                db.execute("ALTER TABLE authorizations ADD COLUMN connection_generation INTEGER")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def approve(self, *, invocation_id: str, repository: str, branch: str,
                operations: set[str], reviewed_by: str,
                target_prs: dict[int, str] | None = None,
                connection_id: str | None = None,
                connection_generation: int | None = None) -> str:
        """Trusted controller records an explicit operator-approved scope."""
        target_prs = target_prs or {}
        if (not all(isinstance(v, str) and v for v in
                    (invocation_id, repository, branch, reviewed_by)) or
                not isinstance(operations, set) or not operations or
                not operations <= (FIRST_SLICE_OPERATIONS |
                                   ({"api_rest_read"} if self.diagnostic_repository_read
                                    else set())) or
                branch.startswith("refs/") or ".." in branch or
                not isinstance(target_prs, dict) or
                any(type(number) is not int or number < 1 or
                    not isinstance(base, str) or not base
                    for number, base in target_prs.items()) or
                ("pr_update" in operations and "pr_create" not in operations and
                 not target_prs) or
                ((connection_id is None) != (connection_generation is None)) or
                (connection_id is not None and
                 (not isinstance(connection_id, str) or not connection_id or
                  type(connection_generation) is not int or connection_generation < 1))):
            raise MediationError("authorization_invalid")
        if connection_id is not None:
            try:
                permitted = (self.connection_authorizer is not None and
                    self.connection_authorizer(connection_id, connection_generation,
                                               repository, reviewed_by) is True)
            except Exception:
                permitted = False
            if not permitted:
                raise MediationError("connection_unavailable")
        reference = secrets.token_urlsafe(32)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO authorizations VALUES (?,NULL,?,?,?,?,?,NULL,?,?,?)",
                       (sha256(reference.encode()).hexdigest(), invocation_id,
                        repository, branch, json.dumps(sorted(operations)), reviewed_by,
                        json.dumps(target_prs, sort_keys=True), connection_id,
                        connection_generation))
        return reference

    def bind_run(self, reference: str, run_id: str, *,
                 allowed_operations: frozenset[str] | None = None) -> dict:
        """Consume approval for one saved runner run; no alternate run may reuse it."""
        if not isinstance(reference, str) or not reference or not isinstance(run_id, str) or not run_id:
            raise MediationError("authorization_unavailable")
        digest = sha256(reference.encode()).hexdigest()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM authorizations WHERE ref_hash=?", (digest,)).fetchone()
            if row is None or row["run_id"] not in (None, run_id):
                raise MediationError("authorization_unavailable")
            if allowed_operations is not None and not set(json.loads(
                    row["operations"])) <= allowed_operations:
                raise MediationError("operation_unavailable_in_runner")
            db.execute("UPDATE authorizations SET run_id=? WHERE ref_hash=?", (run_id, digest))
            return {"invocation_id": row["invocation_id"],
                    "repository": row["repository"], "branch": row["branch"]}

    def authorize_lease(self, lease: dict, request: dict) -> dict | None:
        """Return the canonical scope, atomically fixing its first lease token."""
        run_id, token = lease.get("run_id"), lease.get("token")
        if not isinstance(run_id, str) or not run_id or not isinstance(token, str) or not token:
            return None
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM authorizations WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row["lease_token"] not in (None, token):
                return None
            expected = {key: row[key] for key in ("invocation_id", "repository", "branch")}
            if request != expected:
                return None
            db.execute("UPDATE authorizations SET lease_token=? WHERE run_id=?", (token, run_id))
            return {**expected, "operations": set(json.loads(row["operations"])),
                    "approval_identity": row["reviewed_by"],
                    "connection_id": row["connection_id"],
                    "connection_generation": row["connection_generation"],
                    "target_prs": {int(number): base for number, base in
                                   json.loads(row["target_prs"]).items()}}
