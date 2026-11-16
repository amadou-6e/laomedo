"""Durable idempotent admission around the existing provider resume operation."""

import json
import sqlite3
import threading
from contextlib import contextmanager

from pydantic import ValidationError

from laomedo.agents.agents.base.models import ResumeDispatchRequest
from laomedo.agents.agents.base.utils import _id
from laomedo.agents.errors import RunnerError


class ResumeDispatcher:
    """Reserve before MCP/native effects and never replay uncertain attempts.

    SQLite transactions serialize writers across threads and runner instances.
    Only semantic digests and safe outcomes are persisted, never prompts or
    transient MCP registrations. A reservation surviving its runner remains
    unknown; this journal does not infer that native work stopped.
    """

    def __init__(self, runner):
        self.runner = runner
        self.path = runner.state / "resume-dispatch.sqlite"

    def submit(self, run_id, body, *, response_gate=None):
        """Reserve exactly once, then return an observable asynchronous attempt."""
        _id(run_id)
        self.runner.status(run_id)
        try:
            request = ResumeDispatchRequest.model_validate(body)
        except ValidationError:
            raise RunnerError("invalid_resume_request") from None
        payload = request.to_request()
        manifest = self.runner._mcp_manifest(payload)
        if manifest is not None:
            request.mcp_manifest = manifest.model_dump(mode="json")
        digest = request.digest()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT digest FROM attempts WHERE run_id=? AND attempt_id=?",
                (run_id, request.activity_attempt_id),
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise RunnerError("request_identity_conflict")
                return self._lookup(connection, run_id, request.activity_attempt_id)
            if connection.execute(
                "SELECT 1 FROM attempts WHERE run_id=? AND state IN ('reserved','running','unknown')",
                (run_id,),
            ).fetchone():
                raise RunnerError("resume_already_active")
            connection.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,?,NULL)",
                (
                    run_id,
                    request.activity_attempt_id,
                    digest,
                    self.runner.instance_id,
                    "reserved",
                    None,
                ),
            )
        gate = response_gate or threading.Event()
        if response_gate is None:
            gate.set()
        worker = threading.Thread(
            target=self._execute,
            args=(run_id, request, gate),
            daemon=True,
        )
        try:
            worker.start()
        except Exception:
            self._finish(
                run_id, request.activity_attempt_id, "failed", "runner_runtime_unknown"
            )
            raise RunnerError("runner_runtime_unknown") from None
        return self.lookup(run_id, request.activity_attempt_id)

    def lookup(self, run_id, attempt_id):
        """Observe an admitted attempt, including unknown old-instance work."""
        _id(run_id)
        _id(attempt_id)
        self.runner.status(run_id)
        with self._connection() as connection:
            return self._lookup(connection, run_id, attempt_id)

    @contextmanager
    def _connection(self):
        if self.path.is_symlink():
            raise RunnerError("private_state_must_be_outside_git")
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=10)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS attempts ("
                "run_id TEXT NOT NULL, attempt_id TEXT NOT NULL, digest TEXT NOT NULL, "
                "instance_id TEXT NOT NULL, state TEXT NOT NULL, error_code TEXT, result TEXT, "
                "PRIMARY KEY(run_id,attempt_id))"
            )
            connection.commit()
            with connection:
                yield connection
        except sqlite3.Error:
            raise RunnerError("resume_journal_unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def _lookup(self, connection, run_id, attempt_id):
        row = connection.execute(
            "SELECT instance_id,state,error_code,result FROM attempts "
            "WHERE run_id=? AND attempt_id=?",
            (run_id, attempt_id),
        ).fetchone()
        if row is None:
            raise RunnerError("resume_attempt_not_found")
        state = row[1]
        if row[0] != self.runner.instance_id and state in {"reserved", "running"}:
            state = "unknown"
        return {
            "run_id": run_id,
            "activity_attempt_id": attempt_id,
            "status": state,
            "error_category": row[2],
            "result": json.loads(row[3]) if row[3] else None,
        }

    def _execute(self, run_id, request, gate):
        gate.wait()
        access = None
        attempt = request.activity_attempt_id
        dispatched = False
        state, code, result = "unknown", "runner_runtime_unknown", None
        try:
            with self._connection() as connection:
                connection.execute(
                    "UPDATE attempts SET state='running' WHERE run_id=? AND attempt_id=?",
                    (run_id, attempt),
                )
            body = request.to_request()
            access = self.runner.bind_mcp_resume(run_id, body)
            extra = self.runner.prepare_resume(run_id, body)
            dispatched = True
            result = self.runner.resume(
                run_id,
                request.task,
                expected_post_run_hash=request.expected_post_run_hash,
                expected_thread_id=request.expected_thread_id,
                model=request.model,
                effort=request.effort,
                activity_attempt_id=attempt,
                **extra,
            )
            state, code = "finished", None
        except RunnerError as exc:
            state, code = ("unknown" if dispatched else "failed"), exc.code
        except Exception:
            state, code = "unknown", "runner_runtime_unknown"
        finally:
            try:
                if access is not None:
                    self.runner.release_mcp(run_id, expected=access)
            except Exception:
                state, code = "unknown", "runner_runtime_unknown"
            self._finish(run_id, attempt, state, code, result)

    def _finish(self, run_id, attempt_id, state, code=None, result=None):
        with self._connection() as connection:
            connection.execute(
                "UPDATE attempts SET state=?,error_code=?,result=? "
                "WHERE run_id=? AND attempt_id=?",
                (
                    state,
                    code,
                    json.dumps(result) if result is not None else None,
                    run_id,
                    attempt_id,
                ),
            )
