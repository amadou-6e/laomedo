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


class ExternalOutcomeUnknown(RuntimeError):
    """A dispatched external call may have run, but its result is unconfirmed."""


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
                CREATE TABLE IF NOT EXISTS workflow_invocations (
                    invocation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
                    stage_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_state TEXT NOT NULL,
                    effect_state TEXT NOT NULL,
                    error_class TEXT,
                    native_job_id TEXT,
                    native_job_state TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS trace_receipts (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    invocation_id TEXT NOT NULL REFERENCES workflow_invocations(invocation_id),
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_time TEXT,
                    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
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

    @staticmethod
    def _receipt(db, run_id, invocation_id, kind, payload, source_time=None):
        db.execute("""INSERT INTO trace_receipts
            (run_id, invocation_id, kind, payload_json, source_time)
            VALUES (?, ?, ?, ?, ?)""",
            (run_id, invocation_id, kind, _canonical(payload), source_time))

    def reserve_invocation(self, run_id, stage_id):
        """Reserve first-slice invocation identity before any external dispatch."""
        if not isinstance(stage_id, str) or not stage_id:
            raise LaunchError("invalid_stage_id")
        invocation_id = str(uuid4())
        with self._database() as db:
            run = db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or run["status"] != "reserved":
                raise LaunchError("invocation_not_reserved")
            if db.execute("SELECT 1 FROM workflow_invocations WHERE run_id=?", (run_id,)).fetchone():
                raise LaunchError("first_slice_allows_one_invocation")
            db.execute("""INSERT INTO workflow_invocations
                (invocation_id,run_id,stage_id,status,evidence_state,effect_state,native_job_state)
                VALUES (?,?,?,'reserved','unknown','unknown','unknown')""",
                (invocation_id, run_id, stage_id))
            self._receipt(db, run_id, invocation_id, "invocation_reserved",
                          {"stage_id": stage_id})
        return invocation_id

    def begin_invocation(self, run_id, invocation_id):
        """Commit one dispatch attempt before the caller sends its request."""
        with self._database() as db:
            run_changed = db.execute("""UPDATE runs SET status='dispatching',
                dispatch_attempts=1 WHERE run_id=? AND status='reserved'
                AND dispatch_attempts=0""", (run_id,)).rowcount
            invocation_changed = db.execute("""UPDATE workflow_invocations SET status='running'
                WHERE run_id=? AND invocation_id=? AND status='reserved'""",
                (run_id, invocation_id)).rowcount
            if run_changed != 1 or invocation_changed != 1:
                raise LaunchError("dispatch_not_reserved")
            self._receipt(db, run_id, invocation_id, "dispatch_started", {})

    def record_timeout(self, run_id, invocation_id, *, http_status, detail):
        """A Langflow v2 server 408 ends its wait, not the external effect."""
        if (http_status != 408 or not isinstance(detail, dict) or
                detail.get("code") != "EXECUTION_TIMEOUT"):
            raise LaunchError("not_a_verified_timeout")
        job_id = detail.get("job_id")
        if job_id is not None and (not isinstance(job_id, str) or not job_id):
            raise LaunchError("invalid_native_job_id")
        with self._database() as db:
            run_changed = db.execute("""UPDATE runs SET status='timed_out',
                evidence_complete=0, terminal_reason='langflow_execution_timeout'
                WHERE run_id=? AND status='dispatching'""", (run_id,)).rowcount
            invocation_changed = db.execute("""UPDATE workflow_invocations SET status='failed',
                error_class='timeout', native_job_id=?
                WHERE run_id=? AND invocation_id=? AND status='running'""",
                (job_id, run_id, invocation_id)).rowcount
            if run_changed != 1 or invocation_changed != 1:
                raise LaunchError("timeout_not_dispatching")
            self._receipt(db, run_id, invocation_id, "langflow_execution_timeout",
                          {"http_status": 408, "detail_code": "EXECUTION_TIMEOUT",
                           "native_job_id": job_id, "timeout_layer": "langflow_server"})

    def record_job_status(self, run_id, invocation_id, *, http_status, detail):
        """Distinguish a failed native job from a failed status lookup."""
        if not isinstance(http_status, int) or not isinstance(detail, dict):
            raise LaunchError("invalid_native_status_response")
        with self._database() as db:
            invocation = db.execute("""SELECT native_job_id,native_job_state FROM workflow_invocations
                WHERE run_id=? AND invocation_id=? AND status='failed'""",
                (run_id, invocation_id)).fetchone()
            if invocation is None or not invocation["native_job_id"]:
                raise LaunchError("native_job_not_correlated")
            code = detail.get("code")
            reported_job_id = detail.get("job_id")
            if reported_job_id is not None and reported_job_id != invocation["native_job_id"]:
                raise LaunchError("native_job_id_mismatch")
            observed_state = "failed" if http_status == 500 and code == "JOB_FAILED" else "unknown"
            native_state = ("failed" if invocation["native_job_state"] == "failed"
                            else observed_state)
            db.execute("""UPDATE workflow_invocations SET native_job_state=?
                WHERE run_id=? AND invocation_id=?""",
                (native_state, run_id, invocation_id))
            self._receipt(db, run_id, invocation_id, "native_job_observed",
                          {"http_status": http_status,
                           "detail_code": code if isinstance(code, str) else None,
                           "native_job_id": invocation["native_job_id"],
                           "observation_state": observed_state,
                           "native_job_state": native_state})
        return native_state

    def record_effect(self, run_id, invocation_id, *, source, source_ref, source_time=None):
        """Attach effects after dispatch, including before timeout or after a crash."""
        if (not isinstance(source, str) or not source or
                not isinstance(source_ref, str) or not source_ref):
            raise LaunchError("invalid_effect_source")
        with self._database() as db:
            changed = db.execute("""UPDATE workflow_invocations SET effect_state='observed',
                evidence_state='partial' WHERE run_id=? AND invocation_id=?
                AND status IN ('running','failed') AND EXISTS
                (SELECT 1 FROM runs WHERE run_id=? AND dispatch_attempts=1)""",
                (run_id, invocation_id, run_id)).rowcount
            if changed != 1:
                raise LaunchError("effect_not_correlated")
            self._receipt(db, run_id, invocation_id, "external_effect_observed",
                          {"source": source, "source_ref": source_ref}, source_time)

    def trace_snapshot(self, run_id):
        """Read a durable partial projection without modifying prior receipts."""
        run = self.get(run_id)
        with self._database() as db:
            invocation = db.execute("SELECT * FROM workflow_invocations WHERE run_id=?",
                                    (run_id,)).fetchone()
            if invocation is None:
                raise LaunchError("invocation_not_reserved")
            rows = db.execute("""SELECT sequence,kind,payload_json,source_time,received_at
                FROM trace_receipts WHERE run_id=? ORDER BY sequence""", (run_id,)).fetchall()
        receipts = [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]
        for receipt in receipts:
            del receipt["payload_json"]
        return {"run_id": run_id, "trace_id": run["trace_id"],
                "run_status": run["status"], "dispatch_attempts": run["dispatch_attempts"],
                "evidence_complete": bool(run["evidence_complete"]),
                "invocation": dict(invocation), "receipts": receipts,
                "event_count": len(receipts),
                "last_received_sequence": receipts[-1]["sequence"] if receipts else None,
                "stream_state": "partial" if run["dispatch_attempts"] else "unknown",
                "action_uniqueness": "uncertain"}

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
        except ExternalOutcomeUnknown:
            with self._database() as db:
                db.execute("""UPDATE runs SET status='unknown', evidence_complete=0,
                    terminal_reason='external_outcome_unknown'
                    WHERE run_id=? AND status='dispatching'""", (run_id,))
            raise
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
            db.execute("""UPDATE workflow_invocations SET status='failed',
                evidence_state=CASE WHEN effect_state='observed' THEN 'partial' ELSE 'unknown' END
                WHERE run_id IN (SELECT run_id FROM runs WHERE status='crashed')
                AND status IN ('reserved','running')""")
        return ids
