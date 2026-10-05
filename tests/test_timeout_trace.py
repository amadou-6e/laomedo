"""Effect-aware trace projection of the pinned EXP-65 timeout sequence."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "experiments" / "exp65" / "observation.json"
FLOW = ROOT / "experiments" / "exp03" / "flow.json"


class TimeoutTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "runs.sqlite3"
        self.store = WorkflowRunStore(self.path)
        self.observed = json.loads(OBSERVATION.read_text(encoding="utf-8"))
        self.graph = json.loads(FLOW.read_text(encoding="utf-8"))["data"]
        marker = next(node for node in self.graph["nodes"]
                      if node["id"] == "Exp03Marker-exp03")
        self.code = {marker["id"]: marker["data"]["node"]["template"]["code"]["value"]}

    def reserve(self):
        run = self.store.reserve(graph=self.graph, component_code=self.code,
                                 resolved_config={"case": "server", "source": "EXP-65"},
                                 trigger={"type": "direct"})
        invocation_id = self.store.reserve_invocation(run["run_id"], "synthetic-agent")
        return run, invocation_id

    def timeout(self, run_id, invocation_id):
        caller = self.observed["caller"]
        self.store.record_timeout(run_id, invocation_id,
                                  http_status=caller["status"],
                                  detail=caller["response"])

    @staticmethod
    def native_detail(snapshot, job_id):
        return {"code": snapshot["detail_code"], "job_id": job_id}

    def test_job_failed_before_and_after_late_effect_remains_partial(self):
        run, invocation_id = self.reserve()
        run_id = run["run_id"]
        before = self.store.trace_snapshot(run_id)
        self.assertEqual(before["run_status"], "reserved")
        self.assertEqual(before["dispatch_attempts"], 0)
        self.assertEqual(before["stream_state"], "unknown")
        self.store.begin_invocation(run_id, invocation_id)
        self.timeout(run_id, invocation_id)
        self.assertEqual(self.store.get(run_id)["terminal_reason"],
                         "langflow_execution_timeout")
        job_id = self.observed["caller"]["response"]["job_id"]
        polls = self.observed["status_snapshots"]
        effect = next(row for row in self.observed["runner_events"]
                      if row["event"] == "effect")
        clock_offset = self.observed["clock_before"]["estimated_offset_seconds"]
        effect_host_time = datetime.fromisoformat(effect["utc"]) - timedelta(
            seconds=clock_offset)
        self.assertLess(datetime.fromisoformat(polls[1]["observed_utc"]), effect_host_time)
        self.assertGreater(datetime.fromisoformat(polls[2]["observed_utc"]), effect_host_time)
        self.assertGreater(datetime.fromisoformat(polls[3]["observed_utc"]), effect_host_time)
        for poll in polls[:2]:
            self.assertEqual(self.store.record_job_status(
                run_id, invocation_id, http_status=poll["http_status"],
                detail=self.native_detail(poll, job_id)), "failed")
        prior_effect = self.store.trace_snapshot(run_id)
        self.assertEqual(prior_effect["run_status"], "timed_out")
        self.assertEqual(prior_effect["invocation"]["status"], "failed")
        self.assertEqual(prior_effect["invocation"]["error_class"], "timeout")
        self.assertEqual(prior_effect["invocation"]["native_job_state"], "failed")
        self.assertEqual(prior_effect["invocation"]["effect_state"], "unknown")
        self.assertEqual(prior_effect["invocation"]["evidence_state"], "unknown")
        self.assertFalse(prior_effect["evidence_complete"])

        self.store.record_effect(run_id, invocation_id, source="synthetic-runner",
                                 source_ref="exp65:observation:runner_events:effect",
                                 source_time=effect["utc"])
        for poll in polls[2:]:
            self.assertEqual(self.store.record_job_status(
                run_id, invocation_id, http_status=poll["http_status"],
                detail=self.native_detail(poll, job_id)), "failed")
        reopened = WorkflowRunStore(self.path)
        self.assertEqual(reopened.sweep_crashed(), [])
        trace = reopened.trace_snapshot(run_id)
        self.assertEqual(trace["run_status"], "timed_out")
        self.assertEqual(trace["dispatch_attempts"], 1)
        self.assertEqual(trace["invocation"]["effect_state"], "observed")
        self.assertEqual(trace["invocation"]["evidence_state"], "partial")
        self.assertEqual(trace["invocation"]["native_job_state"], "failed")
        self.assertEqual(trace["stream_state"], "partial")
        self.assertEqual(trace["action_uniqueness"], "uncertain")
        self.assertFalse(trace["evidence_complete"])
        self.assertEqual([r["kind"] for r in trace["receipts"]], [
            "invocation_reserved", "dispatch_started", "langflow_execution_timeout",
            "native_job_observed", "native_job_observed",
            "external_effect_observed", "native_job_observed", "native_job_observed"])
        self.assertEqual(trace["receipts"][2]["payload"]["timeout_layer"],
                         "langflow_server")
        self.assertEqual(trace["event_count"], 8)
        self.assertEqual(trace["last_received_sequence"], trace["receipts"][-1]["sequence"])
        with self.assertRaisesRegex(LaunchError, "dispatch_not_reserved"):
            reopened.begin_invocation(run_id, invocation_id)

    def test_http_500_without_job_failed_code_is_status_unknown(self):
        run, invocation_id = self.reserve()
        self.store.begin_invocation(run["run_id"], invocation_id)
        self.timeout(run["run_id"], invocation_id)
        self.assertEqual(self.store.record_job_status(
            run["run_id"], invocation_id, http_status=500,
            detail={"code": "INTERNAL_SERVER_ERROR"}), "unknown")
        trace = self.store.trace_snapshot(run["run_id"])
        self.assertEqual(trace["invocation"]["native_job_state"], "unknown")
        self.assertEqual(trace["invocation"]["effect_state"], "unknown")
        self.assertNotIn("unique_action_count", trace)

    def test_duplicate_effect_delivery_is_retained_without_unique_count(self):
        run, invocation_id = self.reserve()
        self.store.begin_invocation(run["run_id"], invocation_id)
        self.timeout(run["run_id"], invocation_id)
        for _ in range(2):
            self.store.record_effect(run["run_id"], invocation_id,
                                     source="synthetic-runner",
                                     source_ref="exp65:observation:runner_events:effect",
                                     source_time="2026-10-05T00:00:00Z")
        trace = self.store.trace_snapshot(run["run_id"])
        self.assertEqual(sum(r["kind"] == "external_effect_observed"
                             for r in trace["receipts"]), 2)
        self.assertEqual(trace["action_uniqueness"], "uncertain")
        self.assertNotIn("unique_action_count", trace)

    def test_effect_before_timeout_remains_attached_and_partial(self):
        run, invocation_id = self.reserve()
        run_id = run["run_id"]
        with self.assertRaisesRegex(LaunchError, "effect_not_correlated"):
            self.store.record_effect(run_id, invocation_id, source="synthetic-runner",
                                     source_ref="early")
        self.store.begin_invocation(run_id, invocation_id)
        self.store.record_effect(run_id, invocation_id, source="synthetic-runner",
                                 source_ref="early")
        running = self.store.trace_snapshot(run_id)
        self.assertEqual(running["invocation"]["status"], "running")
        self.assertEqual(running["invocation"]["evidence_state"], "partial")
        self.timeout(run_id, invocation_id)
        reopened = WorkflowRunStore(self.path)
        trace = reopened.trace_snapshot(run_id)
        self.assertEqual(trace["invocation"]["status"], "failed")
        self.assertEqual(trace["invocation"]["effect_state"], "observed")
        self.assertEqual(trace["invocation"]["evidence_state"], "partial")
        self.assertEqual([row["kind"] for row in trace["receipts"]], [
            "invocation_reserved", "dispatch_started", "external_effect_observed",
            "langflow_execution_timeout"])

    def test_effect_after_crash_sweep_attaches_only_to_dispatched_run(self):
        not_dispatched, not_dispatched_invocation = self.reserve()
        dispatched, dispatched_invocation = self.reserve()
        self.store.begin_invocation(dispatched["run_id"], dispatched_invocation)
        self.assertEqual(set(self.store.sweep_crashed()),
                         {not_dispatched["run_id"], dispatched["run_id"]})
        with self.assertRaisesRegex(LaunchError, "effect_not_correlated"):
            self.store.record_effect(not_dispatched["run_id"],
                                     not_dispatched_invocation,
                                     source="synthetic-runner", source_ref="late")
        self.store.record_effect(dispatched["run_id"], dispatched_invocation,
                                 source="synthetic-runner", source_ref="late")
        reopened = WorkflowRunStore(self.path)
        self.assertEqual(reopened.sweep_crashed(), [])
        trace = reopened.trace_snapshot(dispatched["run_id"])
        self.assertEqual(trace["run_status"], "crashed")
        self.assertEqual(trace["dispatch_attempts"], 1)
        self.assertEqual(trace["invocation"]["effect_state"], "observed")
        self.assertEqual(trace["invocation"]["evidence_state"], "partial")
        self.assertEqual(trace["stream_state"], "partial")
        self.assertEqual(reopened.trace_snapshot(not_dispatched["run_id"])["stream_state"],
                         "unknown")

    def test_crash_sweep_keeps_effect_already_observed_while_running(self):
        run, invocation_id = self.reserve()
        run_id = run["run_id"]
        self.store.begin_invocation(run_id, invocation_id)
        self.store.record_effect(run_id, invocation_id,
                                 source="synthetic-runner", source_ref="before-crash")
        self.assertEqual(self.store.sweep_crashed(), [run_id])
        trace = WorkflowRunStore(self.path).trace_snapshot(run_id)
        self.assertEqual(trace["run_status"], "crashed")
        self.assertEqual(trace["invocation"]["evidence_state"], "partial")
        self.assertEqual(trace["invocation"]["effect_state"], "observed")
        self.assertEqual(trace["receipts"][-1]["payload"]["source_ref"], "before-crash")

    def test_later_lookup_error_does_not_downgrade_known_job_failure(self):
        run, invocation_id = self.reserve()
        run_id = run["run_id"]
        self.store.begin_invocation(run_id, invocation_id)
        self.timeout(run_id, invocation_id)
        job_id = self.observed["caller"]["response"]["job_id"]
        self.assertEqual(self.store.record_job_status(
            run_id, invocation_id, http_status=500,
            detail={"code": "JOB_FAILED", "job_id": job_id}), "failed")
        self.assertEqual(self.store.record_job_status(
            run_id, invocation_id, http_status=500,
            detail={"code": "INTERNAL_SERVER_ERROR"}), "failed")
        self.assertEqual(self.store.record_job_status(
            run_id, invocation_id, http_status=0,
            detail={"code": "TRANSPORT_ERROR"}), "failed")
        trace = self.store.trace_snapshot(run_id)
        self.assertEqual(trace["invocation"]["native_job_state"], "failed")
        observations = [row["payload"] for row in trace["receipts"]
                        if row["kind"] == "native_job_observed"]
        self.assertEqual([row["observation_state"] for row in observations],
                         ["failed", "unknown", "unknown"])
        self.assertEqual([row["native_job_state"] for row in observations],
                         ["failed", "failed", "failed"])

    def test_crash_before_or_after_dispatch_never_replays(self):
        first, first_invocation = self.reserve()
        second, second_invocation = self.reserve()
        self.store.begin_invocation(second["run_id"], second_invocation)
        self.assertEqual(set(self.store.sweep_crashed()),
                         {first["run_id"], second["run_id"]})
        for run, invocation_id in ((first, first_invocation), (second, second_invocation)):
            self.assertEqual(self.store.trace_snapshot(run["run_id"])["run_status"], "crashed")
            with self.assertRaisesRegex(LaunchError, "dispatch_not_reserved"):
                self.store.begin_invocation(run["run_id"], invocation_id)
        self.assertEqual(self.store.get(first["run_id"])["dispatch_attempts"], 0)
        self.assertEqual(self.store.get(second["run_id"])["dispatch_attempts"], 1)

    def test_mismatched_job_or_effect_is_refused(self):
        run, invocation_id = self.reserve()
        self.store.begin_invocation(run["run_id"], invocation_id)
        with self.assertRaisesRegex(LaunchError, "not_a_verified_timeout"):
            self.store.record_timeout(run["run_id"], invocation_id,
                                      http_status=500, detail={"code": "JOB_FAILED"})
        self.timeout(run["run_id"], invocation_id)
        with self.assertRaisesRegex(LaunchError, "native_job_id_mismatch"):
            self.store.record_job_status(run["run_id"], invocation_id,
                                         http_status=500,
                                         detail={"code": "JOB_FAILED", "job_id": "other"})
        with self.assertRaisesRegex(LaunchError, "effect_not_correlated"):
            self.store.record_effect(run["run_id"], "other", source="synthetic-runner",
                                     source_ref="exp65:observation:runner_events:effect")
        with self.assertRaisesRegex(LaunchError, "invalid_effect_source"):
            self.store.record_effect(run["run_id"], invocation_id,
                                     source="synthetic-runner", source_ref="")


if __name__ == "__main__":
    unittest.main()
