"""Implementation owned by activity / agent_activity / store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.activity.agent_activity.models import CaptureIdentity

from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import json
import laomedo.activity.agent_activity.utils as _agent_activity_utils
import sqlite3


class ActivityStore:
    def __init__(self, path, *, read_only=False):
        self.path = Path(path).resolve()
        self.read_only = read_only
        if read_only:
            if not self.path.is_file():
                raise LookupError("agent_activity_not_found")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS agent_activity_runs (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL, flow TEXT NOT NULL,
                  node TEXT NOT NULL, provider TEXT NOT NULL, started TEXT NOT NULL,
                  ended TEXT, status TEXT NOT NULL, stream_state TEXT NOT NULL,
                  reason TEXT, native_session TEXT, usage TEXT);
                CREATE INDEX IF NOT EXISTS activity_owner ON agent_activity_runs(owner,flow,node,started);
                CREATE TABLE IF NOT EXISTS agent_activity_receipts (
                  run TEXT NOT NULL, sequence INTEGER NOT NULL, received TEXT NOT NULL,
                  raw TEXT NOT NULL, PRIMARY KEY(run,sequence));
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(agent_activity_runs)")
            }
            for name in ("execution", "runner_run_id", "model", "node_label"):
                if name not in columns:
                    db.execute(
                        f"ALTER TABLE agent_activity_runs ADD COLUMN {name} TEXT"
                    )
            db.execute("""CREATE TABLE IF NOT EXISTS agent_activity_sources (
                run TEXT NOT NULL, source TEXT NOT NULL, cursor INTEGER NOT NULL,
                PRIMARY KEY(run,source,cursor))""")
            db.execute("""CREATE TABLE IF NOT EXISTS agent_activity_attempts (
                runner_run TEXT NOT NULL, attempt TEXT NOT NULL, invocation TEXT NOT NULL,
                PRIMARY KEY(runner_run,attempt))""")

    @contextmanager
    def db(self):
        db = (
            sqlite3.connect(
                self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=15
            )
            if self.read_only
            else sqlite3.connect(self.path, timeout=15)
        )
        db.row_factory = sqlite3.Row
        if self.read_only:
            db.execute("PRAGMA query_only=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self, identity: "CaptureIdentity"):
        from laomedo.activity.agent_activity.models import CaptureIdentity

        if not isinstance(identity, CaptureIdentity):
            raise ValueError("agent_activity_identity_required")
        run = str(uuid4())
        with self.db() as db:
            db.execute(
                """INSERT INTO agent_activity_runs
                (id,owner,flow,node,provider,started,status,stream_state,execution,node_label)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    run,
                    identity.owner,
                    identity.flow,
                    identity.node,
                    identity.provider,
                    _agent_activity_utils.now(),
                    "running",
                    "partial",
                    identity.execution,
                    identity.node_label,
                ),
            )
        return run

    def append(self, run, event, *, source=None, cursor=None):
        if not isinstance(event, dict):
            raise ValueError("agent_activity_event_invalid")
        raw = json.dumps(event, ensure_ascii=False)
        with self.db() as db:
            record = db.execute(
                "SELECT ended FROM agent_activity_runs WHERE id=?", (run,)
            ).fetchone()
            if record is None or record["ended"] is not None:
                raise ValueError("agent_activity_closed")
            if source is not None:
                if not isinstance(cursor, int) or cursor < 1:
                    raise ValueError("agent_activity_cursor_invalid")
                inserted = db.execute(
                    "INSERT OR IGNORE INTO agent_activity_sources VALUES (?,?,?)",
                    (run, source, cursor),
                ).rowcount
                if not inserted:
                    return
            seq = db.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM agent_activity_receipts WHERE run=?",
                (run,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO agent_activity_receipts VALUES (?,?,?,?)",
                (run, seq, _agent_activity_utils.now(), raw),
            )
            if event.get("type") == "thread.started" and isinstance(
                event.get("thread_id"), str
            ):
                db.execute(
                    "UPDATE agent_activity_runs SET native_session=? WHERE id=?",
                    (event["thread_id"], run),
                )
            if event.get("type") == "turn.completed" and isinstance(
                event.get("usage"), dict
            ):
                db.execute(
                    "UPDATE agent_activity_runs SET usage=? WHERE id=?",
                    (json.dumps(event["usage"]), run),
                )

    def bind(self, run, runner_run_id, *, native_session=None, model=None):
        with self.db() as db:
            row = db.execute(
                "SELECT runner_run_id FROM agent_activity_runs WHERE id=?", (run,)
            ).fetchone()
            if row is None or row["runner_run_id"] not in (None, runner_run_id):
                raise ValueError("agent_activity_binding_conflict")
            db.execute(
                "UPDATE agent_activity_runs SET runner_run_id=?,native_session=COALESCE(?,native_session),model=COALESCE(?,model) WHERE id=?",
                (runner_run_id, native_session, model, run),
            )

    def graph_runs(self, owner, flow, execution=None):
        with self.db() as db:
            rows = db.execute(
                """SELECT r.*, (SELECT COUNT(*) FROM agent_activity_receipts e WHERE e.run=r.id) event_count
                FROM agent_activity_runs r WHERE owner=? AND flow=? AND (? IS NULL OR execution=?)
                ORDER BY started DESC,id DESC LIMIT 500""",
                (owner, flow, execution, execution),
            ).fetchall()
        return [{**self._summary(row), "node": row["node"]} for row in rows]

    def claim_attempt(self, invocation, runner_run, attempt):
        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO agent_activity_attempts VALUES (?,?,?)",
                (runner_run, attempt, invocation),
            )
            row = db.execute(
                "SELECT invocation FROM agent_activity_attempts WHERE runner_run=? AND attempt=?",
                (runner_run, attempt),
            ).fetchone()
            return row["invocation"] == invocation

    def finish(self, run, status, *, complete=False, reason=None, ended_at=None):
        if status not in {"completed", "failed", "cancelled", "timed_out"}:
            raise ValueError("agent_activity_status_invalid")
        with self.db() as db:
            db.execute(
                "UPDATE agent_activity_runs SET ended=?,status=?,stream_state=?,reason=? WHERE id=? AND ended IS NULL",
                (
                    ended_at or _agent_activity_utils.now(),
                    status,
                    "complete" if complete else "partial",
                    reason,
                    run,
                ),
            )

    def runs(self, owner, flow, node):
        with self.db() as db:
            rows = db.execute(
                """SELECT r.*, (SELECT COUNT(*) FROM agent_activity_receipts e WHERE e.run=r.id) event_count
                FROM agent_activity_runs r WHERE owner=? AND flow=? AND node=? ORDER BY started DESC,id DESC LIMIT 50""",
                (owner, flow, node),
            ).fetchall()
        return [self._summary(row) for row in rows]

    @staticmethod
    def _summary(row):
        result = dict(row)
        for key in ("owner", "flow", "node"):
            result.pop(key, None)
        result["usage"] = (
            json.loads(result["usage"]) if result["usage"] is not None else None
        )
        result["action_uniqueness"] = "uncertain"
        return result

    def read(self, owner, flow, node, run, after=0, limit=100):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM agent_activity_runs WHERE owner=? AND flow=? AND node=? AND id=?",
                (owner, flow, node, run),
            ).fetchone()
            if row is None:
                raise LookupError("agent_activity_not_found")
            count = db.execute(
                "SELECT COUNT(*) FROM agent_activity_receipts WHERE run=?", (run,)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT sequence,received,raw FROM agent_activity_receipts WHERE run=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run, after, limit),
            ).fetchall()
        events = []
        for item in rows:
            raw = json.loads(item["raw"])
            events.append(
                {
                    "sequence": item["sequence"],
                    "received_at": item["received"],
                    "kind": raw.get("method", raw.get("type", "unknown")),
                    "provenance": "observed",
                    "raw": raw,
                }
            )
        return {
            "run": {**self._summary(row), "event_count": count},
            "events": events,
            "next_after": events[-1]["sequence"] if events else after,
            "has_more": bool(events and events[-1]["sequence"] < count),
        }
