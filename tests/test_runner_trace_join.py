"""Synthetic first-slice native runner correlation; no model turns."""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


class RunnerTraceJoinTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "runs.sqlite3"
        self.store = WorkflowRunStore(self.path)

    def reserve(self):
        run = self.store.reserve(
            graph={"nodes": [{"id": "agent"}]}, component_code={"agent": "code"},
            resolved_config={"model": "synthetic"}, trigger={"type": "direct"})
        invocation = self.store.reserve_invocation(run["run_id"], "agent")
        return run["run_id"], invocation

    def bind(self, run, invocation, runner_run=None):
        runner_run = runner_run or str(uuid4())
        return self.store.bind_runner_ack(
            run, invocation, request_id=invocation, provider="codex",
            runner_run_id=runner_run,
            raw_event_ref=f"laomedo:run:{runner_run}:events")

    def test_exact_replay_conflict_and_cross_invocation(self):
        run, invocation = self.reserve()
        with self.assertRaisesRegex(LaunchError, "runner_ack_without_dispatch"):
            self.bind(run, invocation)
        self.store.begin_invocation(run, invocation)
        native = str(uuid4())
        self.assertTrue(self.bind(run, invocation, native))
        self.assertFalse(self.bind(run, invocation, native))
        with self.assertRaisesRegex(LaunchError, "runner_binding_conflict"):
            self.bind(run, invocation)
        other, other_invocation = self.reserve()
        self.store.begin_invocation(other, other_invocation)
        with self.assertRaisesRegex(LaunchError, "runner_binding_conflict"):
            self.bind(other, other_invocation, native)
        self.assertEqual(sum(row["kind"] == "runner_acknowledged" for row in
                             self.store.trace_snapshot(run)["receipts"]), 1)

    def test_malformed_identity_and_wrong_trace_rejected(self):
        run, invocation = self.reserve()
        self.store.begin_invocation(run, invocation)
        native = str(uuid4())
        for request, reference, error in (
            (str(uuid4()), f"laomedo:run:{native}:events", "runner_request_id_mismatch"),
            (invocation, "file:///private/events", "invalid_runner_reference"),
            (invocation, f"laomedo:run:{uuid4()}:events", "invalid_runner_reference"),
        ):
            with self.assertRaisesRegex(LaunchError, error):
                self.store.bind_runner_ack(run, invocation, request_id=request,
                                           provider="codex", runner_run_id=native,
                                           raw_event_ref=reference)
        other, _ = self.reserve()
        with self.assertRaisesRegex(LaunchError, "runner_ack_without_dispatch"):
            self.store.bind_runner_ack(other, invocation, request_id=invocation,
                                       provider="codex", runner_run_id=native,
                                       raw_event_ref=f"laomedo:run:{native}:events")

    def test_late_ack_after_timeout_and_reopen_without_replay(self):
        run, invocation = self.reserve()
        self.store.begin_invocation(run, invocation)
        self.store.record_timeout(run, invocation, http_status=408,
                                  detail={"code": "EXECUTION_TIMEOUT"})
        native = str(uuid4())
        self.bind(run, invocation, native)
        self.store.record_runner_observation(
            run, invocation, provider="codex", runner_run_id=native,
            kind="runner_cancel", payload={"cancel_requested": True,
                                            "cancel_confirmed": False})
        self.store.record_effect(run, invocation, source="synthetic-runner",
                                 source_ref=f"laomedo:run:{native}:events#effect")
        reopened = WorkflowRunStore(self.path)
        self.assertEqual(reopened.sweep_crashed(), [])
        trace = reopened.trace_snapshot(run)
        self.assertEqual(trace["dispatch_attempts"], 1)
        self.assertEqual(trace["run_status"], "timed_out")
        self.assertEqual(trace["invocation"]["runner_run_id"], native)
        self.assertEqual(trace["invocation"]["evidence_state"], "partial")
        self.assertEqual([r["kind"] for r in trace["receipts"]][-3:],
                         ["runner_acknowledged", "runner_cancel",
                          "external_effect_observed"])
        with self.assertRaisesRegex(LaunchError, "dispatch_not_reserved"):
            reopened.begin_invocation(run, invocation)

    def test_wait_deadline_is_unknown_not_native_cancellation(self):
        run, invocation = self.reserve()
        self.store.begin_invocation(run, invocation)
        self.store.record_runner_wait_uncertain(run, invocation)
        trace = WorkflowRunStore(self.path).trace_snapshot(run)
        self.assertEqual(trace["run_status"], "unknown")
        self.assertEqual(trace["invocation"]["error_class"], "timeout")
        self.assertTrue(trace["receipts"][-1]["payload"]["native_execution_may_continue"])
        self.assertEqual(trace["dispatch_attempts"], 1)
        self.assertEqual(WorkflowRunStore(self.path).sweep_crashed(), [])

    def test_complete_runner_rejection_has_no_native_binding(self):
        run, invocation = self.reserve()
        self.store.begin_invocation(run, invocation)
        self.store.record_runner_rejection(run, invocation, category="invalid_request")
        trace = self.store.trace_snapshot(run)
        self.assertEqual(trace["run_status"], "failed")
        self.assertIsNone(trace["invocation"]["runner_run_id"])
        self.assertEqual(trace["receipts"][-1]["kind"], "runner_rejected")

    def test_existing_database_is_migrated_without_losing_receipts(self):
        legacy = Path(self.temp.name) / "legacy.sqlite3"
        db = sqlite3.connect(legacy)
        try:
            db.execute("""CREATE TABLE workflow_invocations (
                invocation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                stage_id TEXT NOT NULL, status TEXT NOT NULL,
                evidence_state TEXT NOT NULL, effect_state TEXT NOT NULL,
                error_class TEXT, native_job_id TEXT, native_job_state TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            db.execute("""INSERT INTO workflow_invocations VALUES
                ('old-invocation','old-run','agent','failed','partial','observed',
                 NULL,NULL,'unknown','2026-10-05T00:00:00Z')""")
            db.commit()
        finally:
            db.close()
        WorkflowRunStore(legacy)
        WorkflowRunStore(legacy)
        db = sqlite3.connect(legacy)
        try:
            row = db.execute("""SELECT invocation_id,effect_state,runner_request_id,
                runner_run_id FROM workflow_invocations""").fetchone()
        finally:
            db.close()
        self.assertEqual(row, ("old-invocation", "observed", None, None))


if __name__ == "__main__":
    unittest.main()
