"""Synthetic invocation evidence store for EXP-05; not a provider adapter."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


class EvidenceError(RuntimeError):
    pass


class EvidenceStore:
    """Persist identities and raw receipts before deriving projections."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._database() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS invocations (
                    invocation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    stage_id TEXT NOT NULL,
                    native_session_id TEXT,
                    status TEXT NOT NULL,
                    stream_state TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS raw_events (
                    receipt_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    invocation_id TEXT NOT NULL,
                    source_event_id TEXT,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(invocation_id) REFERENCES invocations(invocation_id)
                );
                CREATE TABLE IF NOT EXISTS projections (
                    receipt_sequence INTEGER PRIMARY KEY,
                    invocation_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    FOREIGN KEY(receipt_sequence) REFERENCES raw_events(receipt_sequence)
                );
            """)

    @contextmanager
    def _database(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, *, run_id, trace_id, stage_id, invocation_id):
        if not all(isinstance(value, str) and value for value in
                   (run_id, trace_id, stage_id, invocation_id)):
            raise EvidenceError("invalid_invocation_identity")
        with self._database() as db:
            run = db.execute(
                "SELECT trace_id, status FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None or run["trace_id"] != trace_id or run["status"] != "reserved":
                raise EvidenceError("run_not_reserved")
            try:
                db.execute("""INSERT INTO invocations
                    (invocation_id,run_id,trace_id,stage_id,status,stream_state)
                    VALUES (?,?,?,?,?,?)""",
                    (invocation_id, run_id, trace_id, stage_id, "reserved", "unknown"))
            except sqlite3.IntegrityError as exc:
                raise EvidenceError("duplicate_invocation_identity") from exc

    def record_native_session(self, invocation_id, native_session_id):
        if not isinstance(native_session_id, str) or not native_session_id:
            raise EvidenceError("invalid_native_session")
        with self._database() as db:
            changed = db.execute("""UPDATE invocations
                SET native_session_id=?, status='active'
                WHERE invocation_id=? AND status='reserved'
                AND native_session_id IS NULL""",
                (native_session_id, invocation_id)).rowcount
            if changed != 1:
                raise EvidenceError("native_session_not_reservable")

    def append_raw_event(self, invocation_id, *, source_event_id, kind, payload):
        if not isinstance(kind, str) or not kind or not isinstance(payload, dict):
            raise EvidenceError("invalid_event")
        if source_event_id is not None and (
                not isinstance(source_event_id, str) or not source_event_id):
            raise EvidenceError("invalid_source_event_id")
        with self._database() as db:
            row = db.execute(
                "SELECT status FROM invocations WHERE invocation_id=?", (invocation_id,)
            ).fetchone()
            if row is None or row["status"] != "active":
                raise EvidenceError("invocation_not_active")
            receipt = db.execute("""INSERT INTO raw_events
                (invocation_id,source_event_id,kind,payload_json)
                VALUES (?,?,?,?)""",
                (invocation_id, source_event_id, kind,
                 json.dumps(payload, sort_keys=True, separators=(",", ":"))))
            db.execute("""UPDATE invocations SET stream_state='partial'
                WHERE invocation_id=?""", (invocation_id,))
            return receipt.lastrowid

    def project_unprojected(self):
        """Project only committed raw receipts; never infer missing events."""
        with self._database() as db:
            raw = db.execute("""SELECT r.receipt_sequence,r.invocation_id,r.kind,
                r.payload_json FROM raw_events r
                LEFT JOIN projections p ON p.receipt_sequence=r.receipt_sequence
                WHERE p.receipt_sequence IS NULL ORDER BY r.receipt_sequence""").fetchall()
            for row in raw:
                payload = json.loads(row["payload_json"])
                db.execute("""INSERT INTO projections
                    (receipt_sequence,invocation_id,kind,summary)
                    VALUES (?,?,?,?)""",
                    (row["receipt_sequence"], row["invocation_id"], row["kind"],
                     str(payload.get("summary", ""))))
            return len(raw)

    def mark_complete(self, invocation_id):
        with self._database() as db:
            changed = db.execute("""UPDATE invocations
                SET status='completed',stream_state='complete'
                WHERE invocation_id=? AND status='active'""", (invocation_id,)).rowcount
            if changed != 1:
                raise EvidenceError("invocation_not_active")

    def sweep_crashed(self):
        """A restart terminates unfinished invocations; it never resumes them."""
        with self._database() as db:
            ids = [row[0] for row in db.execute("""SELECT invocation_id
                FROM invocations WHERE status IN ('reserved','active')
                ORDER BY invocation_id""")]
            db.execute("""UPDATE invocations SET status='crashed'
                WHERE status IN ('reserved','active')""")
        self.project_unprojected()
        return ids

    def inspect(self):
        with self._database() as db:
            return {
                "invocations": [dict(row) for row in db.execute(
                    "SELECT * FROM invocations ORDER BY invocation_id")],
                "raw_events": [dict(row) for row in db.execute(
                    "SELECT * FROM raw_events ORDER BY receipt_sequence")],
                "projections": [dict(row) for row in db.execute(
                    "SELECT * FROM projections ORDER BY receipt_sequence")],
            }
