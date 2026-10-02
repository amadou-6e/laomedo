"""Durable first-dispatch reservation for the Langflow integration boundary.

This store is a local prototype. It does not execute providers or grant access.
"""

from hashlib import sha256
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value):
    return "sha256:" + sha256(_canonical(value).encode("utf-8")).hexdigest()


class LaunchError(RuntimeError):
    pass


class WorkflowRunStore:
    """SQLite-backed launch identities; crash recovery never replays dispatch."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._database() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL UNIQUE,
                    graph_revision TEXT NOT NULL,
                    component_revisions TEXT NOT NULL,
                    resolved_config_ref TEXT NOT NULL,
                    frozen_graph TEXT NOT NULL,
                    resolved_config TEXT NOT NULL,
                    trigger_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dispatch_attempts INTEGER NOT NULL DEFAULT 0,
                    evidence_complete INTEGER NOT NULL DEFAULT 0,
                    terminal_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS synthetic_dispatches (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _database(self):
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, *, graph, component_code, resolved_config, trigger):
        if (not isinstance(graph, dict) or not graph.get("nodes") or
                not isinstance(component_code, dict) or not component_code or
                not isinstance(resolved_config, dict) or not resolved_config or
                not isinstance(trigger, dict) or not trigger):
            raise LaunchError("unresolved_launch_identity")
        ids = {str(node.get("id")) for node in graph["nodes"] if isinstance(node, dict)}
        if not ids or any(node_id not in ids or not isinstance(code, str) or not code
                          for node_id, code in component_code.items()):
            raise LaunchError("unresolved_component_identity")
        component_revisions = {node_id: "sha256:" + sha256(code.encode("utf-8")).hexdigest()
                               for node_id, code in component_code.items()}
        run_id, trace_id = str(uuid4()), str(uuid4())
        record = (run_id, trace_id, _digest(graph), _canonical(component_revisions),
                  _digest(resolved_config), _canonical(graph), _canonical(resolved_config),
                  _canonical(trigger), "reserved")
        try:
            with self._database() as db:
                db.execute("""INSERT INTO runs
                    (run_id, trace_id, graph_revision, component_revisions,
                     resolved_config_ref, frozen_graph, resolved_config, trigger_json, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", record)
        except (OSError, sqlite3.Error) as exc:
            raise LaunchError("launch_record_not_durable") from exc
        return self.get(run_id)

    def get(self, run_id):
        with self._database() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise LaunchError("unknown_run")
        result = dict(row)
        result["component_revisions"] = json.loads(result["component_revisions"])
        return result

    def dispatch(self, run_id, callback):
        """Commit a conservative attempt before calling the synthetic stage."""
        with self._database() as db:
            changed = db.execute("""UPDATE runs SET status='dispatching',
                dispatch_attempts=dispatch_attempts+1
                WHERE run_id=? AND status='reserved' AND dispatch_attempts=0
                AND graph_revision<>'' AND resolved_config_ref<>'' AND trace_id<>''""",
                (run_id,)).rowcount
            if changed != 1:
                raise LaunchError("dispatch_not_reserved")
        try:
            result = callback(run_id)
        except Exception:
            with self._database() as db:
                db.execute("""UPDATE runs SET status='failed', terminal_reason='synthetic_error'
                    WHERE run_id=? AND status='dispatching'""", (run_id,))
            raise
        with self._database() as db:
            db.execute("""UPDATE runs SET status='completed', evidence_complete=1,
                terminal_reason=NULL WHERE run_id=? AND status='dispatching'""", (run_id,))
        return result

    def record_synthetic_dispatch(self, run_id):
        """Durable monotonic counter for a deterministic test callback only."""
        with self._database() as db:
            db.execute("INSERT INTO synthetic_dispatches(run_id) VALUES (?)", (run_id,))
            return db.execute("SELECT max(sequence) FROM synthetic_dispatches").fetchone()[0]

    def counters(self):
        with self._database() as db:
            return {"runs": db.execute("SELECT count(*) FROM runs").fetchone()[0],
                    "dispatch_attempts": db.execute("SELECT coalesce(sum(dispatch_attempts),0) FROM runs").fetchone()[0],
                    "synthetic_dispatches": db.execute("SELECT count(*) FROM synthetic_dispatches").fetchone()[0]}

    def sweep_crashed(self):
        """Startup reconciliation. Never redispatch the old run."""
        with self._database() as db:
            ids = [row[0] for row in db.execute("""SELECT run_id FROM runs
                WHERE status IN ('reserved','dispatching') ORDER BY created_at, run_id""")]
            db.execute("""UPDATE runs SET status='crashed', evidence_complete=0,
                terminal_reason='backend_restart'
                WHERE status IN ('reserved','dispatching')""")
        return ids
