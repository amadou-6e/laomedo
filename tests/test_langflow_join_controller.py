"""Credential-free controller races for the proposed Playground join."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch
from uuid import uuid4

from laomedo.langflow_join import LangflowJoinController
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


class FakeRunner:
    def __init__(self):
        self.starts = []
        self.cancels = []
        self.records = {}
        self.entered = Event()
        self.release = Event()
        self.release.set()
        self.fail_after_record = False

    def start_async(self, body):
        request_id = body["request_id"]
        canonical = {key: value for key, value in body.items()
                     if key != "request_id"}
        digest = "sha256:" + sha256(json.dumps(
            canonical, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode()).hexdigest()
        run_id = str(uuid4())
        record = {"client_request_id": request_id, "request_hash": digest,
                  "provider": "codex", "run_id": run_id,
                  "raw_event_ref": f"laomedo:run:{run_id}:events",
                  "status": "prepared"}
        self.records[request_id] = record
        self.starts.append(request_id)
        self.entered.set()
        if self.fail_after_record:
            raise TimeoutError("synthetic_lost_response")
        if not self.release.wait(5):
            raise TimeoutError("synthetic_ack_stall")
        return dict(record)

    def lookup_request(self, request_id):
        if request_id not in self.records:
            raise LookupError("request_not_found")
        return dict(self.records[request_id])

    def status(self, run_id):
        return dict(next(record for record in self.records.values()
                         if record["run_id"] == run_id))

    def cancel(self, run_id):
        record = next(record for record in self.records.values()
                      if record["run_id"] == run_id)
        self.cancels.append(run_id)
        record.update(status="cancelled", cancel_requested=True,
                      cancel_confirmed=True)
        return dict(record)


class LangflowJoinControllerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = WorkflowRunStore(Path(temporary.name) / "runs.sqlite3")
        self.runner = FakeRunner()
        self.export = {"id": "saved-flow", "data": {"nodes": [{"id": "agent",
            "data": {"node": {"template": {"code": {"value": "synthetic code"}}}}}]}}
        self.controller = LangflowJoinController(
            self.store, self.runner, lambda _flow: self.export)

    def start(self, client=None, task="synthetic task"):
        return self.controller.start(
            client_request_id=client or str(uuid4()), flow_id="saved-flow",
            graph_run_id="reported-graph", stage_id="agent",
            runner_body={"task": task, "model": "synthetic",
                         "effort": "low", "skill_ref": {"skill_id": "fixture"}})

    def test_stop_before_start_refuses_runner_dispatch(self):
        client = str(uuid4())
        self.assertEqual(self.controller.cancel(client)["status"], "pending_start")
        record = self.start(client)
        self.assertEqual(record["status"], "cancelled")
        self.assertEqual(record["dispatch_attempts"], 0)
        self.assertEqual(self.runner.starts, [])
        reopened = WorkflowRunStore(self.store.path)
        self.assertEqual(reopened.langflow_client_snapshot(client)["run_status"],
                         "cancelled")

    def test_lost_ack_reconciles_cancel_without_second_start(self):
        client = str(uuid4())
        self.runner.fail_after_record = True
        with self.assertRaisesRegex(LaunchError, "runner_start_unknown"):
            self.start(client)
        trace = self.store.trace_snapshot(
            self.store.langflow_client_snapshot(client)["run_id"])
        self.assertEqual(trace["dispatch_attempts"], 1)
        self.assertIsNone(trace["invocation"]["runner_run_id"])
        self.controller.cancel(client)
        self.assertEqual(len(self.runner.starts), 1)
        self.assertEqual(len(self.runner.cancels), 1)
        reopened = WorkflowRunStore(self.store.path)
        self.assertEqual(reopened.langflow_client_snapshot(client)["runner_run_id"],
                         self.runner.cancels[0])
        self.assertEqual(self.start(client)["dispatch_attempts"], 1)
        self.assertEqual(len(self.runner.starts), 1)

    def test_stop_during_held_ack_uses_request_lookup_and_cancels_once(self):
        client = str(uuid4())
        self.runner.release.clear()
        outcome = []

        def worker():
            try:
                outcome.append(self.start(client))
            except Exception as exc:
                outcome.append(exc)

        thread = Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(self.runner.entered.wait(3))
            pending = self.controller.cancel(client)
            self.assertEqual(pending["runner_run_id"], self.runner.cancels[0])
        finally:
            self.runner.release.set()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.runner.starts), 1)
        self.assertEqual(len(self.runner.cancels), 1)
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], dict)
        with self.assertRaisesRegex(LaunchError, "client_request_identity_conflict"):
            self.start(client, task="changed task")

    def test_not_found_during_inflight_post_stays_pending_then_cancels(self):
        client = str(uuid4())
        entered, release = Event(), Event()
        original = self.runner.start_async
        outcome = []

        def held_before_native_record(body):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("synthetic_transport_stall")
            return original(body)

        def worker():
            try:
                outcome.append(self.start(client))
            except Exception as exc:
                outcome.append(exc)

        with patch.object(self.runner, "start_async",
                          side_effect=held_before_native_record):
            thread = Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                pending = self.controller.cancel(client)
                self.assertEqual(pending["status"], "cancel_pending_runner_lookup")
                self.assertIsNone(pending["runner_run_id"])
                self.assertEqual(self.runner.starts, [])
            finally:
                release.set()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome[0], dict)
        self.assertEqual(len(self.runner.starts), 1)
        self.assertEqual(len(self.runner.cancels), 1)
        self.assertEqual(self.store.trace_snapshot(outcome[0]["run_id"])["run_status"],
                         "cancelled")

    def test_stop_wins_before_atomic_begin_and_no_native_post_occurs(self):
        client = str(uuid4())
        entered, release = Event(), Event()
        original = self.store.begin_langflow_client
        outcome = []

        def delayed_begin(request_id):
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("synthetic_begin_stall")
            return original(request_id)

        def worker():
            outcome.append(self.start(client))

        with patch.object(self.store, "begin_langflow_client",
                          side_effect=delayed_begin):
            thread = Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.controller.cancel(client)["status"],
                                 "cancelled")
            finally:
                release.set()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome[0]["status"], "cancelled")
        self.assertEqual(outcome[0]["dispatch_attempts"], 0)
        self.assertEqual(self.runner.starts, [])

    def test_mismatched_ack_with_stop_reconciles_exact_native_request(self):
        client = str(uuid4())
        original = self.runner.start_async

        def mismatched_ack(body):
            ack = original(body)
            self.store.request_langflow_cancel(client)
            return {**ack, "request_hash": "sha256:" + "0" * 64}

        with patch.object(self.runner, "start_async", side_effect=mismatched_ack):
            with self.assertRaisesRegex(LaunchError,
                                        "runner_ack_identity_mismatch"):
                self.start(client)
        self.assertEqual(len(self.runner.starts), 1)
        self.assertEqual(len(self.runner.cancels), 1)
        self.assertEqual(self.controller.status(client)["native_status"],
                         "cancelled")

    def test_late_native_record_is_cancelled_on_status_reconciliation(self):
        client = str(uuid4())
        with patch.object(self.runner, "start_async",
                          side_effect=TimeoutError("synthetic_unknown")):
            with self.assertRaisesRegex(LaunchError, "runner_start_unknown"):
                self.start(client)
        pending = self.controller.cancel(client)
        self.assertEqual(pending["status"], "cancel_pending_runner_lookup")
        binding = self.store.langflow_client_snapshot(client)
        native_run = str(uuid4())
        invocation = binding["invocation_id"]
        self.runner.records[invocation] = {
            "client_request_id": invocation,
            "request_hash": binding["runner_request_hash"],
            "provider": "codex", "run_id": native_run,
            "raw_event_ref": f"laomedo:run:{native_run}:events",
            "status": "prepared"}
        observed = self.controller.status(client)
        self.assertEqual(observed["runner_run_id"], native_run)
        self.assertEqual(len(self.runner.cancels), 1)
        self.assertEqual(self.store.trace_snapshot(binding["run_id"])["run_status"],
                         "cancelled")

    def test_saved_flow_mismatch_refuses_without_runner_attempt(self):
        self.export["id"] = "other-flow"
        with self.assertRaisesRegex(LaunchError, "saved_flow_identity_mismatch"):
            self.start()
        self.assertEqual(self.runner.starts, [])
        self.assertEqual(self.store.counters()["dispatch_attempts"], 0)

    def test_native_terminal_is_durable_without_semantic_evidence(self):
        client = str(uuid4())
        started = self.start(client)
        native = self.runner.records[started["invocation_id"]]
        native.update(status="completed", answer="synthetic answer")
        observed = self.controller.status(client)
        self.assertEqual(observed["native_status"], "completed")
        trace = self.store.trace_snapshot(started["run_id"])
        self.assertEqual(trace["run_status"], "completed")
        self.assertEqual(self.store.get(started["run_id"])["completion_basis"],
                         "native_runner_status")
        self.assertFalse(trace["evidence_complete"])
        self.assertEqual(sum(item["kind"] == "runner_terminal"
                             for item in trace["receipts"]), 1)
        self.controller.status(client)
        self.assertEqual(sum(item["kind"] == "runner_terminal"
                             for item in self.store.trace_snapshot(
                                 started["run_id"])["receipts"]), 1)


if __name__ == "__main__":
    unittest.main()
