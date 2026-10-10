"""Durable first-dispatch reservation for the Langflow integration boundary.

This store is a local prototype. It does not execute providers or grant access.
"""

from hashlib import sha256
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from uuid import UUID


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
                    completion_basis TEXT,
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
                    runner_request_id TEXT,
                    runner_request_hash TEXT,
                    runner_provider TEXT,
                    runner_run_id TEXT,
                    runner_raw_event_ref TEXT,
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
                CREATE TABLE IF NOT EXISTS langflow_client_requests (
                    client_request_id TEXT PRIMARY KEY,
                    client_request_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
                    invocation_id TEXT NOT NULL UNIQUE REFERENCES workflow_invocations(invocation_id),
                    flow_id TEXT,
                    graph_run_id TEXT,
                    graph_basis TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS langflow_cancel_intents (
                    client_request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
            """)
            # Preserve stores created before native runner correlation existed.
            columns = {row[1] for row in db.execute("PRAGMA table_info(workflow_invocations)")}
            for column in ("runner_request_id", "runner_request_hash",
                           "runner_provider", "runner_run_id",
                           "runner_raw_event_ref"):
                if column not in columns:
                    db.execute(f"ALTER TABLE workflow_invocations ADD COLUMN {column} TEXT")
            run_columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            if "completion_basis" not in run_columns:
                db.execute("ALTER TABLE runs ADD COLUMN completion_basis TEXT")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS unique_runner_binding
                ON workflow_invocations(runner_provider, runner_run_id)
                WHERE runner_run_id IS NOT NULL""")

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
                (invocation_id,run_id,stage_id,status,evidence_state,effect_state,
                 native_job_state,runner_request_id)
                VALUES (?,?,?,'reserved','unknown','unknown','unknown',?)""",
                (invocation_id, run_id, stage_id, invocation_id))
            self._receipt(db, run_id, invocation_id, "invocation_reserved",
                          {"stage_id": stage_id, "runner_request_id": invocation_id})
        return invocation_id

    def freeze_runner_request(self, run_id, invocation_id, request_hash):
        """Commit the exact native POST-body digest before dispatch."""
        if (not isinstance(request_hash, str) or len(request_hash) != 71 or
                not request_hash.startswith("sha256:") or
                any(c not in "0123456789abcdef" for c in request_hash[7:])):
            raise LaunchError("invalid_runner_request_hash")
        with self._database() as db:
            changed = db.execute("""UPDATE workflow_invocations
                SET runner_request_hash=? WHERE run_id=? AND invocation_id=?
                AND status='reserved' AND runner_request_hash IS NULL""",
                (request_hash, run_id, invocation_id)).rowcount
            if changed != 1:
                raise LaunchError("runner_request_not_reserved")
            self._receipt(db, run_id, invocation_id, "runner_request_frozen",
                          {"request_hash": request_hash})

    @staticmethod
    def _client_uuid(value):
        try:
            normalized = str(UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            raise LaunchError("invalid_client_request_id") from None
        if normalized != value:
            raise LaunchError("invalid_client_request_id")
        return normalized

    def claim_langflow_client(self, client_request_id, client_request_hash, *,
                              run_id, invocation_id, flow_id=None,
                              graph_run_id=None, graph_basis="repository_fixture"):
        """Bind one client retry key before any runner POST.

        The run and invocation must already be reserved and frozen. If another
        claimant won the same key, return its binding and cancel the losing
        reservation before it can dispatch.
        """
        client_request_id = self._client_uuid(client_request_id)
        if (not isinstance(client_request_hash, str) or
                len(client_request_hash) != 71 or
                not client_request_hash.startswith("sha256:") or
                any(c not in "0123456789abcdef" for c in client_request_hash[7:])):
            raise LaunchError("invalid_client_request_hash")
        if graph_basis not in {"saved_flow_export", "repository_fixture"}:
            raise LaunchError("invalid_graph_basis")
        if flow_id is not None and (not isinstance(flow_id, str) or not flow_id):
            raise LaunchError("invalid_flow_id")
        if graph_run_id is not None and (not isinstance(graph_run_id, str) or not graph_run_id):
            raise LaunchError("invalid_graph_run_id")
        with self._database() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("""SELECT * FROM langflow_client_requests
                WHERE client_request_id=?""", (client_request_id,)).fetchone()
            if existing is not None:
                if existing["client_request_hash"] != client_request_hash:
                    raise LaunchError("client_request_identity_conflict")
                if existing["run_id"] != run_id:
                    changed = db.execute("""UPDATE runs SET status='cancelled',
                        terminal_reason='duplicate_client_reservation'
                        WHERE run_id=? AND status='reserved' AND dispatch_attempts=0""",
                        (run_id,)).rowcount
                    invocation_changed = db.execute("""UPDATE workflow_invocations
                        SET status='cancelled' WHERE run_id=? AND invocation_id=?
                        AND status='reserved'""", (run_id, invocation_id)).rowcount
                    if changed != 1 or invocation_changed != 1:
                        raise LaunchError("duplicate_reservation_not_reserved")
                    self._receipt(db, run_id, invocation_id,
                                  "duplicate_reservation_discarded",
                                  {"client_request_id": client_request_id})
                return dict(existing), False
            frozen = db.execute("""SELECT 1 FROM workflow_invocations
                WHERE run_id=? AND invocation_id=? AND status='reserved'
                AND runner_request_hash IS NOT NULL""", (run_id, invocation_id)).fetchone()
            if frozen is None:
                raise LaunchError("client_request_not_frozen")
            try:
                db.execute("""INSERT INTO langflow_client_requests
                    (client_request_id,client_request_hash,run_id,invocation_id,
                     flow_id,graph_run_id,graph_basis)
                    VALUES (?,?,?,?,?,?,?)""",
                    (client_request_id, client_request_hash, run_id, invocation_id,
                     flow_id, graph_run_id, graph_basis))
            except sqlite3.IntegrityError as exc:
                raise LaunchError("client_request_binding_conflict") from exc
            self._receipt(db, run_id, invocation_id, "langflow_client_claimed",
                          {"client_request_id": client_request_id,
                           "flow_id": flow_id, "graph_run_id": graph_run_id,
                           "graph_basis": graph_basis,
                           "executing_graph_verified": False})
            row = db.execute("""SELECT * FROM langflow_client_requests
                WHERE client_request_id=?""", (client_request_id,)).fetchone()
            return dict(row), True

    def langflow_client_snapshot(self, client_request_id):
        client_request_id = self._client_uuid(client_request_id)
        with self._database() as db:
            row = db.execute("""SELECT c.*,r.status AS run_status,
                r.dispatch_attempts,w.runner_request_hash,w.runner_run_id,
                w.runner_provider,w.runner_raw_event_ref
                FROM langflow_client_requests c JOIN runs r ON r.run_id=c.run_id
                JOIN workflow_invocations w ON w.invocation_id=c.invocation_id
                WHERE c.client_request_id=?""", (client_request_id,)).fetchone()
        return dict(row) if row is not None else None

    def langflow_runner_binding(self, runner_run_id):
        try:
            runner_run_id = str(UUID(str(runner_run_id)))
        except (TypeError, ValueError, AttributeError):
            raise LaunchError("invalid_runner_identity") from None
        with self._database() as db:
            row = db.execute("""SELECT c.*,w.runner_run_id,w.runner_request_hash
                FROM langflow_client_requests c JOIN workflow_invocations w
                ON w.invocation_id=c.invocation_id
                WHERE w.runner_provider='codex' AND w.runner_run_id=?""",
                (runner_run_id,)).fetchone()
        return dict(row) if row is not None else None

    def request_langflow_cancel(self, client_request_id):
        """Persist Stop even when the first bridge acknowledgement is absent."""
        client_request_id = self._client_uuid(client_request_id)
        with self._database() as db:
            inserted = db.execute("""INSERT OR IGNORE INTO langflow_cancel_intents
                (client_request_id) VALUES (?)""", (client_request_id,)).rowcount == 1
            row = db.execute("""SELECT run_id,invocation_id FROM langflow_client_requests
                WHERE client_request_id=?""", (client_request_id,)).fetchone()
            if row is not None and inserted:
                self._receipt(db, row["run_id"], row["invocation_id"],
                              "langflow_cancel_requested",
                              {"client_request_id": client_request_id})
        return self.langflow_client_snapshot(client_request_id)

    def langflow_cancel_requested(self, client_request_id):
        client_request_id = self._client_uuid(client_request_id)
        with self._database() as db:
            return db.execute("""SELECT 1 FROM langflow_cancel_intents
                WHERE client_request_id=?""", (client_request_id,)).fetchone() is not None

    def begin_langflow_client(self, client_request_id):
        """Atomically choose no POST after Stop, or one permitted POST attempt."""
        client_request_id = self._client_uuid(client_request_id)
        with self._database() as db:
            # Serialize the first read with request_langflow_cancel's write.
            # A plain SELECT here can otherwise race a Stop intent and let
            # both cancellation and dispatch commit for one invocation.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT c.run_id,c.invocation_id,r.status,
                r.dispatch_attempts,w.runner_request_hash FROM langflow_client_requests c
                JOIN runs r ON r.run_id=c.run_id
                JOIN workflow_invocations w ON w.invocation_id=c.invocation_id
                WHERE c.client_request_id=?""", (client_request_id,)).fetchone()
            if row is None:
                raise LaunchError("client_request_not_claimed")
            if row["dispatch_attempts"]:
                return "already_dispatching"
            if row["status"] == "cancelled":
                return "cancelled_before_dispatch"
            if row["status"] != "reserved" or not row["runner_request_hash"]:
                raise LaunchError("client_request_not_frozen")
            cancelled = db.execute("""SELECT 1 FROM langflow_cancel_intents
                WHERE client_request_id=?""", (client_request_id,)).fetchone()
            if cancelled is not None:
                db.execute("UPDATE runs SET status='cancelled',terminal_reason='client_cancelled_before_dispatch' WHERE run_id=?",
                           (row["run_id"],))
                db.execute("UPDATE workflow_invocations SET status='cancelled' WHERE invocation_id=?",
                           (row["invocation_id"],))
                self._receipt(db, row["run_id"], row["invocation_id"],
                              "client_cancelled_before_dispatch", {})
                return "cancelled_before_dispatch"
            db.execute("""UPDATE runs SET status='dispatching',dispatch_attempts=1
                WHERE run_id=?""", (row["run_id"],))
            db.execute("""UPDATE workflow_invocations SET status='running'
                WHERE invocation_id=?""", (row["invocation_id"],))
            self._receipt(db, row["run_id"], row["invocation_id"],
                          "dispatch_started", {})
            return "dispatching"

    def bind_runner_ack(self, run_id, invocation_id, *, request_id, provider,
                        runner_run_id, raw_event_ref):
        """Persist one exact native acknowledgement without replaying dispatch."""
        try:
            UUID(str(request_id))
            UUID(str(runner_run_id))
        except (TypeError, ValueError, AttributeError):
            raise LaunchError("invalid_runner_identity") from None
        if (provider != "codex" or
                raw_event_ref != f"laomedo:run:{runner_run_id}:events"):
            raise LaunchError("invalid_runner_reference")
        with self._database() as db:
            row = db.execute("""SELECT runner_request_id,runner_provider,runner_run_id,
                runner_raw_event_ref FROM workflow_invocations
                WHERE run_id=? AND invocation_id=?""", (run_id, invocation_id)).fetchone()
            attempts = db.execute("SELECT dispatch_attempts FROM runs WHERE run_id=?",
                                  (run_id,)).fetchone()
            if row is None or attempts is None or attempts[0] != 1:
                raise LaunchError("runner_ack_without_dispatch")
            if request_id != row["runner_request_id"]:
                raise LaunchError("runner_request_id_mismatch")
            binding = (provider, runner_run_id, raw_event_ref)
            existing = (row["runner_provider"], row["runner_run_id"],
                        row["runner_raw_event_ref"])
            if existing == binding:
                return False
            if any(existing):
                raise LaunchError("runner_binding_conflict")
            try:
                db.execute("""UPDATE workflow_invocations SET runner_provider=?,
                    runner_run_id=?,runner_raw_event_ref=?
                    WHERE run_id=? AND invocation_id=?""",
                    (*binding, run_id, invocation_id))
            except sqlite3.IntegrityError as exc:
                raise LaunchError("runner_binding_conflict") from exc
            self._receipt(db, run_id, invocation_id, "runner_acknowledged",
                          {"runner_request_id": request_id, "runner_provider": provider,
                           "runner_run_id": runner_run_id,
                           "raw_event_ref": raw_event_ref})
        return True

    def record_runner_observation(self, run_id, invocation_id, *, provider,
                                  runner_run_id, kind, payload):
        """Append runner status/cancel evidence under the existing trace identity."""
        if kind not in {"runner_status", "runner_cancel"} or not isinstance(payload, dict):
            raise LaunchError("invalid_runner_observation")
        with self._database() as db:
            row = db.execute("""SELECT 1 FROM workflow_invocations
                WHERE run_id=? AND invocation_id=? AND runner_provider=? AND runner_run_id=?""",
                (run_id, invocation_id, provider, runner_run_id)).fetchone()
            if row is None:
                raise LaunchError("runner_observation_not_correlated")
            self._receipt(db, run_id, invocation_id, kind,
                          {"runner_provider": provider, "runner_run_id": runner_run_id,
                           "observation": payload})

    def record_runner_terminal(self, run_id, invocation_id, *, provider,
                               runner_run_id, status):
        """Project a verified native terminal state without claiming output truth."""
        if status not in {"completed", "cancelled", "failed", "timeout", "interrupted"}:
            raise LaunchError("invalid_runner_terminal_status")
        projected = "failed" if status in {"timeout", "interrupted"} else status
        with self._database() as db:
            row = db.execute("""SELECT r.status AS run_status,w.runner_run_id
                FROM runs r JOIN workflow_invocations w ON w.run_id=r.run_id
                WHERE r.run_id=? AND w.invocation_id=? AND
                w.runner_provider=? AND w.runner_run_id=?""",
                (run_id, invocation_id, provider, runner_run_id)).fetchone()
            if row is None:
                raise LaunchError("runner_terminal_not_correlated")
            if row["run_status"] == projected:
                return False
            if row["run_status"] not in {"dispatching", "incomplete"}:
                raise LaunchError("runner_terminal_conflict")
            db.execute("""UPDATE runs SET status=?,evidence_complete=0,
                completion_basis='native_runner_status',terminal_reason=?
                WHERE run_id=?""", (projected, "native_runner_" + status, run_id))
            db.execute("""UPDATE workflow_invocations SET status=?,error_class=?
                WHERE run_id=? AND invocation_id=?""",
                ("completed" if status == "completed" else "failed",
                 None if status == "completed" else "native_runner_" + status,
                 run_id, invocation_id))
            self._receipt(db, run_id, invocation_id, "runner_terminal",
                          {"runner_provider": provider, "runner_run_id": runner_run_id,
                           "native_status": status, "semantic_output_verified": False})
            return True

    def record_runner_wait_uncertain(self, run_id, invocation_id):
        """A wait deadline is not evidence that the native run stopped."""
        with self._database() as db:
            changed = db.execute("""UPDATE runs SET status='incomplete',
                evidence_complete=0, terminal_reason='runner_result_pending'
                WHERE run_id=? AND status='dispatching' AND dispatch_attempts=1""",
                (run_id,)).rowcount
            if changed != 1:
                raise LaunchError("runner_wait_not_dispatching")
            db.execute("""UPDATE workflow_invocations SET status='failed',
                error_class='timeout' WHERE run_id=? AND invocation_id=?
                AND status='running'""", (run_id, invocation_id))
            self._receipt(db, run_id, invocation_id, "runner_result_pending",
                          {"native_execution_may_continue": True})

    def record_runner_failure(self, run_id, invocation_id, *, category):
        """Retain any post-dispatch uncertainty, including runner 409 conflicts."""
        allowed = {"runner_request_conflict", "runner_ack_identity_mismatch",
                   "runner_binding_conflict", "runner_binding_write_error",
                   "runner_transport_error",
                   "runner_dispatch_error", "runner_lookup_unknown",
                   "runner_lookup_conflict", "runner_lookup_mismatch"}
        if category not in allowed:
            raise LaunchError("invalid_runner_failure_category")
        with self._database() as db:
            row = db.execute("""SELECT status,dispatch_attempts FROM runs WHERE run_id=?""",
                             (run_id,)).fetchone()
            invocation = db.execute("""SELECT 1 FROM workflow_invocations
                WHERE run_id=? AND invocation_id=?""", (run_id, invocation_id)).fetchone()
            if row is None or invocation is None or row["dispatch_attempts"] != 1:
                raise LaunchError("runner_failure_without_dispatch")
            if row["status"] == "dispatching":
                db.execute("""UPDATE runs SET status='incomplete',evidence_complete=0,
                    terminal_reason=? WHERE run_id=?""", (category, run_id))
                db.execute("""UPDATE workflow_invocations SET status='failed',
                    error_class='provider' WHERE run_id=? AND invocation_id=?
                    AND status='running'""", (run_id, invocation_id))
            self._receipt(db, run_id, invocation_id, "runner_failure",
                          {"category": category, "native_execution_may_continue": True})

    def record_runner_rejection(self, run_id, invocation_id, *, category):
        """A complete client rejection has no runner identity to bind."""
        if not isinstance(category, str) or not category:
            raise LaunchError("invalid_runner_rejection")
        with self._database() as db:
            changed = db.execute("""UPDATE runs SET status='failed',
                terminal_reason='runner_rejected' WHERE run_id=? AND status='dispatching'
                AND dispatch_attempts=1""", (run_id,)).rowcount
            invocation_changed = db.execute("""UPDATE workflow_invocations
                SET status='failed',error_class='runner_rejected'
                WHERE run_id=? AND invocation_id=? AND status='running'""",
                (run_id, invocation_id)).rowcount
            if changed != 1 or invocation_changed != 1:
                raise LaunchError("runner_rejection_not_correlated")
            self._receipt(db, run_id, invocation_id, "runner_rejected",
                          {"error_category": category})

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

    def dispatch(self, run_id, callback, *, completion_basis="callback_result"):
        """Commit one attempt; distinguish a returned callback from process exit."""
        if completion_basis not in {"callback_result", "process_exit"}:
            raise LaunchError("completion_basis_invalid")
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
            db.execute("""UPDATE runs SET status='completed', evidence_complete=?,
                completion_basis=?, terminal_reason=NULL
                WHERE run_id=? AND status='dispatching'""",
                (int(completion_basis == "callback_result"), completion_basis, run_id))
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
