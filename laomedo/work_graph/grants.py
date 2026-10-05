"""Single-user host grant ledger for local Work Graph stage launches.

Keep this ledger outside Git and outside every agent-visible container mount.
The issuer belongs to the host controller, never to a Langflow component.
"""

from contextlib import closing
import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from uuid import uuid4

from laomedo.workflow_run_store import LaunchError
from .launch import relevant_content_digest
from .model import GraphSnapshot


def _private_path(path):
    target = Path(path).expanduser()
    if not target.is_absolute() or target.is_symlink():
        raise LaunchError("grant_store_path_invalid")
    resolved = target.resolve()
    if any((parent / ".git").exists() for parent in (resolved.parent, *resolved.parent.parents)):
        raise LaunchError("grant_store_inside_git")
    return resolved


def _host_principal():
    if os.name != "nt":
        return "uid:" + str(os.getuid())
    try:
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True, text=True, encoding="utf-8", timeout=5)
        rows = list(csv.reader(result.stdout.splitlines()))
        sid = rows[0][-1] if result.returncode == 0 and len(rows) == 1 else ""
    except (OSError, subprocess.TimeoutExpired, IndexError):
        sid = ""
    if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
        raise LaunchError("host_operator_identity_unavailable")
    return "sid:" + sid


class LocalGrantAuthority:
    """Issue on the host, then atomically redeem a one-use launch grant."""

    def __init__(self, path):
        self.path = _private_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS grants (
                grant_id TEXT PRIMARY KEY,
                work_key TEXT NOT NULL,
                graph_snapshot_id TEXT NOT NULL,
                runner TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                timeout_seconds INTEGER NOT NULL,
                max_turns INTEGER NOT NULL,
                operator_id TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                redeemed_at TEXT,
                content_digest TEXT
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(grants)")}
            if "content_digest" not in columns:
                db.execute("ALTER TABLE grants ADD COLUMN content_digest TEXT")
        if not self.path.is_file():
            raise LaunchError("grant_store_unavailable")
        self.path.chmod(0o600)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def issue(self, *, work_key, graph_snapshot, expires_at,
              timeout_seconds, max_turns):
        """Record the authenticated host process principal, not a caller label."""
        if (not all(isinstance(value, str) and value.strip() for value in
                    (work_key, expires_at)) or
                not isinstance(graph_snapshot, GraphSnapshot) or
                not graph_snapshot.source_complete or
                work_key not in {item.key for item in graph_snapshot.items} or
                type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600 or
                type(max_turns) is not int or max_turns != 0):
            raise LaunchError("grant_issue_invalid")
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            raise LaunchError("grant_expiry_invalid") from None
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise LaunchError("grant_expired")
        grant_id = str(uuid4())
        operator_id = _host_principal()
        content_digest = relevant_content_digest(graph_snapshot, work_key)
        with closing(self._connect()) as db, db:
            db.execute("""INSERT INTO grants
                (grant_id, work_key, graph_snapshot_id, runner, scope,
                 expires_at, timeout_seconds, max_turns, operator_id,
                 issued_at, redeemed_at, content_digest)
                VALUES (?, ?, ?, 'langflow-local', 'stage-launch',
                        ?, ?, ?, ?, ?, NULL, ?)""",
                (grant_id, work_key, graph_snapshot.snapshot_id, expires_at,
                 timeout_seconds, max_turns, operator_id,
                 datetime.now(timezone.utc).isoformat(), content_digest))
        return grant_id

    def __call__(self, grant_id, binding):
        """Return only nonsecret fields, consuming a matching grant once."""
        if not isinstance(grant_id, str) or not isinstance(binding, dict):
            raise LaunchError("grant_invalid")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
            if row is None or row["redeemed_at"] is not None:
                raise LaunchError("grant_invalid")
            if row["operator_id"] != _host_principal():
                raise LaunchError("grant_operator_mismatch")
            if (row["work_key"] != binding.get("work_snapshot", {}).get("key") or
                    not row["content_digest"] or
                    row["content_digest"] != binding.get("selected_content_digest")):
                raise LaunchError("grant_binding_mismatch")
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                raise LaunchError("grant_expired")
            db.execute("UPDATE grants SET redeemed_at=? WHERE grant_id=? AND redeemed_at IS NULL",
                       (datetime.now(timezone.utc).isoformat(), grant_id))
        return {"grant_id": grant_id, "operator_authorized": True,
                "work_key": row["work_key"],
                "graph_snapshot_id": row["graph_snapshot_id"],
                "content_digest": row["content_digest"],
                "runner": row["runner"], "scope": row["scope"],
                "expires_at": row["expires_at"],
                "limits": {"timeout_seconds": row["timeout_seconds"],
                           "max_turns": row["max_turns"]}}
