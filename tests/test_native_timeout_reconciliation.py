"""Real-boundary state controls, without credentials or model calls."""
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from laomedo.workflow_run_store import WorkflowRunStore, LaunchError
from laomedo.handoff_http import RunnerAdapter
from laomedo.runner_trace_bridge import RunnerTraceBridge
from laomedo.handoffs import HandoffError, envelope

class NativeTimeoutReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "store.db"
        self.store = WorkflowRunStore(self.path)
        self.run = self.store.reserve(graph={"nodes": [{"id": "agent"}]},
            component_code={"agent": "code"}, resolved_config={"fixture": True},
            trigger={"type": "direct"})["run_id"]
        self.inv = self.store.reserve_invocation(self.run, "agent")
        self.store.begin_invocation(self.run, self.inv)
        self.native = str(uuid4())
        self.store.bind_runner_ack(self.run, self.inv, request_id=self.inv,
            provider="codex", runner_run_id=self.native,
            raw_event_ref=f"laomedo:run:{self.native}:events")

    def terminal(self, status="cancelled", confirmed=True, native=None):
        return self.store.record_runner_terminal(self.run, self.inv,
            provider="codex", runner_run_id=native or self.native,
            status=status, cancel_confirmed=confirmed)

    def effect(self):
        self.store.record_effect(self.run, self.inv, source="fixture",
            source_ref="sha256:" + "1" * 64, source_time="2026-10-09T00:00:00Z")

    def assert_retained(self, expected_status, observed=True):
        trace = WorkflowRunStore(self.path).trace_snapshot(self.run)
        self.assertEqual(trace["run_status"], expected_status)
        self.assertEqual(trace["dispatch_attempts"], 1)
        self.assertEqual(trace["stream_state"], "partial")
        self.assertFalse(trace["evidence_complete"])
        self.assertEqual(trace["invocation"]["effect_state"], "observed" if observed else "unknown")
        self.assertEqual(trace["invocation"]["error_class"], "timeout" if expected_status != "crashed" else None)
        receipt = next(r for r in trace["receipts"] if r["kind"] == "runner_terminal")
        self.assertTrue(receipt["payload"]["workflow_outcome_preserved"])
        return trace

    def test_concurrent_same_terminal_observation_has_one_durable_receipt(self):
        self.store.record_runner_wait_uncertain(self.run, self.inv)
        gate = threading.Barrier(2)
        def observe(_):
            gate.wait(timeout=5)
            return self.terminal()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(observe, range(2)))
        self.assertEqual(sorted(outcomes), [False, True])
        rows = [r for r in self.store.trace_snapshot(self.run)["receipts"]
                if r["kind"] == "runner_terminal"]
        self.assertEqual(len(rows), 1)

    def test_server_timeout_then_late_effect_and_confirmed_cancel_survive_restart(self):
        self.store.record_timeout(self.run, self.inv, http_status=408,
            detail={"code": "EXECUTION_TIMEOUT", "job_id": "job"})
        self.store.record_job_status(self.run, self.inv, http_status=500,
            detail={"code": "JOB_FAILED", "job_id": "job"})
        self.effect()
        self.terminal()
        self.assertFalse(self.terminal())
        self.assert_retained("timed_out")

    def test_wait_timeout_before_effect_then_cancel_does_not_claim_no_effect(self):
        self.store.record_runner_wait_uncertain(self.run, self.inv)
        self.terminal()
        self.assert_retained("incomplete", observed=False)

    def test_effect_before_timeout_is_not_erased_by_native_completion(self):
        self.effect()
        self.store.record_runner_wait_uncertain(self.run, self.inv)
        self.terminal(status="completed", confirmed=False)
        self.assert_retained("incomplete")

    def test_crash_and_late_effect_keep_original_crash_projection(self):
        self.store.sweep_crashed()
        self.effect()
        self.terminal()
        self.assert_retained("crashed")

    def test_unconfirmed_cancellation_never_projects_confirmed_cancelled(self):
        self.terminal(confirmed=False)
        trace = self.store.trace_snapshot(self.run)
        self.assertEqual(trace["run_status"], "incomplete")
        self.assertFalse(trace["receipts"][-1]["payload"]["cancel_confirmed"])
        self.terminal(confirmed=True)
        self.assertEqual(self.store.trace_snapshot(self.run)["run_status"], "cancelled")
        with self.assertRaisesRegex(LaunchError, "runner_terminal_conflict"):
            self.terminal(confirmed=False)

    def test_conflicting_or_wrong_native_identity_is_rejected(self):
        self.terminal()
        with self.assertRaisesRegex(LaunchError, "runner_terminal_conflict"):
            self.terminal(status="completed")
        with self.assertRaisesRegex(LaunchError, "runner_terminal_not_correlated"):
            self.terminal(native=str(uuid4()))

    def adapter(self):
        token = Path(self.temp.name) / "token"
        token.write_text("a" * 64)
        return RunnerAdapter({"codex": "http://127.0.0.1:1"}, {"codex": token})

    def test_authenticated_status_whitelists_fields_and_rejects_wrong_run(self):
        adapter = self.adapter()
        def response(req, **kwargs):
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.get_header("Authorization"), "Bearer " + "a" * 64)
            return io.BytesIO(json.dumps({"run_id": self.native, "status": "cancelled",
                "cancel_confirmed": True, "task": "PRIVATE", "auth": "SECRET"}).encode())
        with patch("laomedo.handoff_http.urlopen", side_effect=response):
            value = adapter.status("codex", self.native)
        self.assertNotIn("PRIVATE", str(value))
        self.assertNotIn("SECRET", str(value))
        with patch("laomedo.handoff_http.urlopen", return_value=io.BytesIO(
                json.dumps({"run_id": str(uuid4())}).encode())):
            with self.assertRaisesRegex(HandoffError, "runner_status_identity_mismatch"):
                adapter.status("codex", self.native)

    def test_bridge_reconciles_without_replay_and_forwards_confirmation(self):
        self.store.record_runner_wait_uncertain(self.run, self.inv)
        adapter = self.adapter()
        bridge = RunnerTraceBridge(self.store, adapter)
        with patch.object(adapter, "status", return_value={"run_id": self.native,
                "status": "cancelled", "cancel_confirmed": False}) as status:
            bridge.observe_terminal(self.run, self.inv)
            status.assert_called_once_with("codex", self.native)
        self.assertFalse(self.store.trace_snapshot(self.run)["receipts"][-1]["payload"]["cancel_confirmed"])
        with patch.object(adapter, "status", return_value={"run_id": self.native,
                "status": "cancelled", "cancel_confirmed": True}):
            bridge.observe_terminal(self.run, self.inv)
        self.assert_retained("incomplete", observed=False)
        with patch.object(adapter, "status") as status:
            with self.assertRaisesRegex(LaunchError, "runner_observation_not_correlated"):
                bridge.observe_terminal(self.run, str(uuid4()))
            status.assert_not_called()

    def test_poll_timeout_maps_to_wait_expiry_only_when_deadline_passed(self):
        handoff = envelope(None, {"provider": "codex", "model": "fixture", "effort": "low"},
                           "task", skills=[{"skill_id": "fixture", "revision_id": "sha256:" + "a"*64}])
        for poll_time, error in [(2.0, HandoffError), (0.5, TimeoutError)]:
            with self.subTest(poll_time=poll_time):
                now = [0.0]
                def respond(req, **kwargs):
                    if req.get_method() == "POST":
                        body = json.loads(req.data)
                        return io.BytesIO(json.dumps({"run_id": self.native, "status": "running",
                            "client_request_id": body["request_id"],
                            "raw_event_ref": f"laomedo:run:{self.native}:events"}).encode())
                    now[0] = poll_time
                    raise TimeoutError("fixture")
                with patch("laomedo.handoff_http.time.monotonic", side_effect=lambda: now[0]), \
                        patch("laomedo.handoff_http.urlopen", side_effect=respond):
                    with self.assertRaises(error):
                        self.adapter().dispatch(handoff, deadline=1.0, cancelled=threading.Event(), early_start=True)

if __name__ == "__main__":
    unittest.main()
