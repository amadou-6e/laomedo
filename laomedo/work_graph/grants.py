"""Single-user host grant ledger for local Work Graph stage launches.

Keep this ledger outside Git and outside every agent-visible container mount.
The issuer belongs to the host controller, never to a Langflow component.
"""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

from laomedo.workflow_run_store import LaunchError


def _private_path(path):
    target = Path(path).expanduser()
    if not target.is_absolute() or target.is_symlink():
        raise LaunchError("grant_store_path_invalid")
    resolved = target.resolve()
    if any((parent / ".git").exists() for parent in (resolved.parent, *resolved.parent.parents)):
        raise LaunchError("grant_store_inside_git")
    return resolved


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
                redeemed_at TEXT
            )""")
        if not self.path.is_file():
            raise LaunchError("grant_store_unavailable")
        self.path.chmod(0o600)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def issue(self, *, work_key, graph_snapshot_id, operator_id, expires_at,
              timeout_seconds, max_turns):
        """Record a host decision; caller must establish operator authority."""
        if (not all(isinstance(value, str) and value.strip() for value in
                    (work_key, graph_snapshot_id, operator_id, expires_at)) or
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
        with closing(self._connect()) as db, db:
            db.execute("""INSERT INTO grants VALUES
                (?, ?, ?, 'langflow-local', 'stage-launch', ?, ?, ?, ?, ?, NULL)""",
                (grant_id, work_key, graph_snapshot_id, expires_at,
                 timeout_seconds, max_turns, operator_id,
                 datetime.now(timezone.utc).isoformat()))
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
            if (row["work_key"] != binding.get("work_snapshot", {}).get("key") or
                    row["graph_snapshot_id"] != binding.get("selected_graph_snapshot_id")):
                raise LaunchError("grant_binding_mismatch")
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                raise LaunchError("grant_expired")
            db.execute("UPDATE grants SET redeemed_at=? WHERE grant_id=? AND redeemed_at IS NULL",
                       (datetime.now(timezone.utc).isoformat(), grant_id))
        return {"grant_id": grant_id, "operator_authorized": True,
                "work_key": row["work_key"],
                "graph_snapshot_id": row["graph_snapshot_id"],
                "runner": row["runner"], "scope": row["scope"],
                "expires_at": row["expires_at"],
                "limits": {"timeout_seconds": row["timeout_seconds"],
                           "max_turns": row["max_turns"]}}
