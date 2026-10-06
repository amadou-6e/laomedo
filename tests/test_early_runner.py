"""Credential-free falsifiers for issue #22's durable early identity."""

import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib import error as http_error, request as http_request
from uuid import uuid4

from laomedo.local_runner import LocalRunner, RunnerError, _json, serve
import laomedo.local_runner as runner_module
from laomedo.handoff_http import RunnerAdapter
from laomedo.runner_trace_bridge import RunnerTraceBridge
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore
from laomedo.handoffs import HandoffError, envelope
from laomedo.skill_store import SkillStore
from test_local_runner import FakeServer


class BlockingServer(FakeServer):
    entered = threading.Event()
    closed = threading.Event()
    turn_starts = 0

    def request(self, method, params, timeout=30):
        if method == "turn/start":
            type(self).turn_starts += 1
        return super().request(method, params, timeout)

    def wait_turn(self, turn_id, timeout, cancelled):
        self.log.write('{"method":"item/started"}\n')
        self.log.flush()
        type(self).entered.set()
        if not cancelled.wait(4):
            return "timeout", "synthetic_timeout"
        return "cancelled", "cancelled_by_user"

    def close(self):
        super().close()
        type(self).closed.set()


class EarlyRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        source = root / "source"
        source.mkdir()
        (root / ".git").mkdir()
        (source / "input.txt").write_text("synthetic", encoding="utf-8")
        skill = root / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: fixture\n---\nSynthetic.\n",
                                        encoding="utf-8")
        store = SkillStore(root.parent / (root.name + "-skills"))
        self.addCleanup(lambda: shutil.rmtree(store.root, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(store.draft_root, ignore_errors=True))
        revision = store.import_skill("fixture", skill)
        self.state = root.parent / (root.name + "-state")
        self.addCleanup(lambda: shutil.rmtree(self.state, ignore_errors=True))
        self.source, self.store = source, store
        self.runner = LocalRunner(self.state, store.root, source,
                                  transport=BlockingServer, check_docker=False,
                                  max_model_turns=2)
        BlockingServer.entered = threading.Event()
        BlockingServer.closed = threading.Event()
        BlockingServer.turn_starts = 0
        self.body = {"request_id": str(uuid4()), "task": "Synthetic task",
                     "model": "test-model", "effort": "low",
                     "skill_ref": {"skill_id": "fixture",
                                   "revision_id": revision["revision_id"],
                                   "tree_hash": revision["tree_hash"]}}

    def start_http(self):
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(),
                                 thread.join(2)))
        return f"http://127.0.0.1:{server.server_port}/v1/runs"

    def call(self, url, *, body=None, method="POST"):
        headers = {"Authorization": "Bearer " + self.runner.api_token,
                   "Content-Type": "application/json"}
        req = http_request.Request(url, data=None if body is None else
                                   json.dumps(body).encode(), headers=headers,
                                   method=method)
        try:
            with http_request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except http_error.HTTPError as exc:
            return exc.code, json.load(exc)

    def wait_status(self, run_id, status):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            record = self.runner.status(run_id)
            if record["status"] == status:
                return record
            time.sleep(.02)
        self.fail(f"run {run_id} did not reach {status}")

    def test_preworker_cancel_and_same_request_retry_never_dispatch(self):
        gate = threading.Event()
        first = self.runner.start_async(self.body, response_gate=gate)
        self.assertEqual(first["status"], "prepared")
        self.assertEqual(self.runner.status(first["run_id"])["run_id"], first["run_id"])
        self.assertEqual(self.runner.start_async(self.body)["run_id"], first["run_id"])
        self.assertFalse((self.state / "turn-ledger.json").exists())
        changed = {**self.body, "task": "different"}
        with self.assertRaisesRegex(RunnerError, "request_identity_conflict"):
            self.runner.start_async(changed)
        cancelled = self.runner.cancel(first["run_id"])
        self.assertTrue(cancelled["cancel_confirmed"])
        gate.set()
        time.sleep(.1)
        self.assertEqual(self.runner.status(first["run_id"])["status"], "cancelled")
        self.assertEqual(BlockingServer.turn_starts, 0)
        self.assertFalse((self.state / "turn-ledger.json").exists())

    def test_http_ack_before_turn_completion_and_active_cancel(self):
        base = self.start_http()
        code, ack = self.call(base + "/async", body=self.body)
        self.assertEqual(code, 202)
        run_id = ack["run_id"]
        self.assertIn(ack["status"], {"prepared", "running"})
        self.assertTrue(BlockingServer.entered.wait(3))
        code, duplicate = self.call(base + "/async", body=self.body)
        self.assertEqual((code, duplicate["run_id"]), (202, run_id))
        code, conflict = self.call(base + "/async", body={**self.body, "task": "other"})
        self.assertEqual((code, conflict["error_category"]),
                         (409, "request_identity_conflict"))
        code, accepted = self.call(base + "/" + run_id + "/cancel", body={})
        self.assertEqual(code, 202)
        self.assertTrue(accepted["cancel_requested"])
        self.assertFalse(accepted["cancel_confirmed"])
        self.assertTrue(self.runner.status(run_id)["cancel_requested"])
        final = self.wait_status(run_id, "cancelled")
        self.assertTrue(final["cancel_confirmed"])
        code, terminal_retry = self.call(base + "/async", body=self.body)
        self.assertEqual((code, terminal_retry["run_id"], terminal_retry["status"]),
                         (202, run_id, "cancelled"))
        self.assertEqual(BlockingServer.turn_starts, 1)
        self.assertEqual(json.loads((self.state / "turn-ledger.json").read_text())
                         ["attempted_turns"], 1)
        self.assertIn("item/started", (self.runner._run_dir(run_id) /
                                       "raw-events.jsonl").read_text())
        code, polled = self.call(base + "/" + run_id, method="GET")
        self.assertEqual((code, polled["status"]), (200, "cancelled"))

    def test_restart_fences_pending_worker_and_exact_retry(self):
        gate = threading.Event()
        first = self.runner.start_async(self.body, response_gate=gate)
        restarted = LocalRunner(self.state, self.store.root, self.source,
                                transport=BlockingServer, check_docker=False,
                                max_model_turns=2)
        self.assertEqual(restarted.status(first["run_id"])["status"], "interrupted")
        self.assertEqual(restarted.start_async(self.body)["run_id"], first["run_id"])
        gate.set()
        time.sleep(.1)
        self.assertEqual(restarted.status(first["run_id"])["status"], "interrupted")
        self.assertEqual(BlockingServer.turn_starts, 0)
        self.assertFalse((self.state / "turn-ledger.json").exists())

    def test_cancel_during_initialization_prevents_thread_and_turn(self):
        entered, release = threading.Event(), threading.Event()
        class Initializing(BlockingServer):
            def request(self, method, params, timeout=30):
                if method == "model/list":
                    entered.set()
                    if not release.wait(3):
                        raise AssertionError("initialization_not_released")
                return super().request(method, params, timeout)
        self.runner.transport = Initializing
        first = self.runner.start_async(self.body)
        self.assertTrue(entered.wait(2))
        accepted = self.runner.cancel(first["run_id"])
        self.assertTrue(accepted["cancel_requested"])
        self.assertFalse(accepted["cancel_confirmed"])
        release.set()
        final = self.wait_status(first["run_id"], "cancelled")
        self.assertTrue(final["cancel_confirmed"])
        self.assertIsNone(final["thread_id"])
        self.assertEqual(Initializing.turn_starts, 0)
        self.assertFalse((self.state / "turn-ledger.json").exists())

    def test_restart_of_saved_active_record_is_interrupted_not_replayed(self):
        body = {key: value for key, value in self.body.items() if key != "request_id"}
        record = self.runner._prepare(body, client_request_id=self.body["request_id"],
                                      request_hash="sha256:synthetic-record")
        record["status"] = "running"
        _json(self.runner._run_dir(record["run_id"]) / "record.json", record)
        restarted = LocalRunner(self.state, self.store.root, self.source,
                                transport=BlockingServer, check_docker=False,
                                max_model_turns=2)
        self.assertEqual(restarted.status(record["run_id"])["status"], "interrupted")
        self.assertEqual(BlockingServer.turn_starts, 0)
        self.assertFalse((self.state / "turn-ledger.json").exists())

    def test_controller_adapter_exposes_id_before_wait_and_can_cancel(self):
        base = self.start_http()
        adapter = RunnerAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                {"codex": self.state / "api-token"})
        skill = self.body["skill_ref"]
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task", skills=[skill])
        acknowledged, outcome = [], {}
        cancelled = threading.Event()
        def submit():
            outcome["value"] = adapter.dispatch(handoff, deadline=time.monotonic() + 5,
                                                cancelled=cancelled, early_start=True,
                                                on_ack=acknowledged.append)
        worker = threading.Thread(target=submit)
        worker.start()
        self.assertTrue(BlockingServer.entered.wait(3))
        self.assertEqual(len(acknowledged), 1)
        run_id = acknowledged[0]["run_id"]
        self.assertEqual(adapter.active[handoff["execution_id"]][1], run_id)
        accepted = adapter.cancel(handoff["execution_id"])
        self.assertTrue(accepted["cancel_requested"])
        self.assertFalse(accepted["cancel_confirmed"])
        cancelled.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome["value"]["run_id"], run_id)
        self.assertEqual(outcome["value"]["status"], "cancelled")
        self.assertTrue(self.runner.status(run_id)["cancel_confirmed"])
        self.assertEqual(BlockingServer.turn_starts, 1)

    def test_trace_bridge_binds_real_local_http_ack_and_cancel(self):
        base = self.start_http()
        adapter = RunnerAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                {"codex": self.state / "api-token"})
        trace_path = Path(self.temp.name) / "trace.sqlite3"
        trace = WorkflowRunStore(trace_path)
        run = trace.reserve(graph={"nodes": [{"id": "agent"}]},
                            component_code={"agent": "synthetic"},
                            resolved_config={"model": "test-model"},
                            trigger={"type": "direct"})
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task",
                           skills=[self.body["skill_ref"]])
        bridge = RunnerTraceBridge(trace, adapter)
        cancelled = threading.Event()
        outcome = {}
        def submit():
            outcome["value"] = bridge.dispatch(
                run["run_id"], "agent", handoff,
                deadline=time.monotonic() + 5, cancelled=cancelled)
        worker = threading.Thread(target=submit)
        worker.start()
        try:
            self.assertTrue(BlockingServer.entered.wait(3))
            ack_deadline = time.monotonic() + 3
            snapshot = WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
            while (snapshot["invocation"]["runner_run_id"] is None and
                   time.monotonic() < ack_deadline):
                time.sleep(.01)
                snapshot = WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
            binding = snapshot["invocation"]
            self.assertEqual(binding["runner_request_id"], binding["invocation_id"])
            self.assertEqual(binding["runner_run_id"],
                             adapter.active[handoff["execution_id"]][1])
            self.assertEqual(self.runner.status(binding["runner_run_id"])
                             ["client_request_id"], binding["runner_request_id"])
            accepted = bridge.cancel(run["run_id"], binding["invocation_id"],
                                     handoff["execution_id"])
            self.assertTrue(accepted["cancel_requested"])
            cancelled.set()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcome["value"][0], binding["invocation_id"])
            reopened = WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
            kinds = [row["kind"] for row in reopened["receipts"]]
            self.assertIn("runner_acknowledged", kinds)
            self.assertIn("runner_cancel", kinds)
            self.assertIn("runner_status", kinds)
            self.assertEqual(reopened["dispatch_attempts"], 1)
            self.assertEqual(BlockingServer.turn_starts, 1)
        finally:
            cancelled.set()
            adapter.cancel(handoff["execution_id"])
            worker.join(5)

    def test_lost_ack_reconciles_by_get_without_second_start(self):
        base = self.start_http()
        class DroppedAckAdapter(RunnerAdapter):
            def dispatch(self, handoff, **kwargs):
                kwargs["on_ack"] = lambda _: None
                return super().dispatch(handoff, **kwargs)
        adapter = DroppedAckAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                    {"codex": self.state / "api-token"})
        trace_path = Path(self.temp.name) / "lost-ack.sqlite3"
        trace = WorkflowRunStore(trace_path)
        run = trace.reserve(graph={"nodes": [{"id": "agent"}]},
                            component_code={"agent": "synthetic"},
                            resolved_config={"model": "test-model"},
                            trigger={"type": "direct"})
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task",
                           skills=[self.body["skill_ref"]])
        bridge = RunnerTraceBridge(trace, adapter)
        try:
            with self.assertRaisesRegex(HandoffError, "runner_result_pending"):
                bridge.dispatch(run["run_id"], "agent", handoff,
                                deadline=time.monotonic() + 3,
                                cancelled=threading.Event())
            before = WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
            invocation = before["invocation"]
            self.assertEqual(before["run_status"], "incomplete")
            self.assertIsNone(invocation["runner_run_id"])
            self.assertTrue(BlockingServer.entered.wait(3))
            self.assertEqual(BlockingServer.turn_starts, 1)
            native_id = adapter.active[handoff["execution_id"]][1]
            code, lookup = self.call(base.rsplit("/v1/runs", 1)[0] +
                                     "/v1/requests/" + invocation["runner_request_id"],
                                     method="GET")
            self.assertEqual(code, 200)
            self.assertEqual(lookup["run_id"], native_id)
            self.assertNotIn("task", lookup)
            self.assertNotIn("profile", lookup)
            self.assertEqual(lookup["request_hash"], invocation["runner_request_hash"])
            bridge = RunnerTraceBridge(WorkflowRunStore(trace_path), adapter)
            found = bridge.reconcile(run["run_id"], invocation["invocation_id"],
                                     handoff["execution_id"])
            self.assertEqual(found["run_id"], native_id)
            again = bridge.reconcile(run["run_id"], invocation["invocation_id"],
                                     handoff["execution_id"])
            self.assertEqual(again["run_id"], native_id)
            self.assertEqual(BlockingServer.turn_starts, 1)
            after = WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
            self.assertEqual(after["invocation"]["runner_run_id"], native_id)
            self.assertEqual(sum(r["kind"] == "runner_acknowledged"
                                 for r in after["receipts"]), 1)
            bridge.cancel(run["run_id"], invocation["invocation_id"],
                          handoff["execution_id"])
        finally:
            adapter.cancel(handoff["execution_id"])

    def test_binding_write_failure_can_reconcile_same_native_run(self):
        base = self.start_http()
        adapter = RunnerAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                {"codex": self.state / "api-token"})
        trace_path = Path(self.temp.name) / "binding-failure.sqlite3"
        trace = WorkflowRunStore(trace_path)
        run = trace.reserve(graph={"nodes": [{"id": "agent"}]},
                            component_code={"agent": "synthetic"},
                            resolved_config={"model": "test-model"},
                            trigger={"type": "direct"})
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task",
                           skills=[self.body["skill_ref"]])
        bridge = RunnerTraceBridge(trace, adapter)
        try:
            with patch.object(trace, "bind_runner_ack",
                              side_effect=LaunchError("injected_write_failure")):
                with self.assertRaisesRegex(LaunchError, "injected_write_failure"):
                    bridge.dispatch(run["run_id"], "agent", handoff,
                                    deadline=time.monotonic() + 5,
                                    cancelled=threading.Event())
            before = WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
            invocation = before["invocation"]
            self.assertEqual(before["run_status"], "incomplete")
            self.assertEqual(before["receipts"][-1]["payload"]["category"],
                             "runner_binding_write_error")
            self.assertIsNone(invocation["runner_run_id"])
            native_id = adapter.active[handoff["execution_id"]][1]
            bridge.reconcile(run["run_id"], invocation["invocation_id"],
                             handoff["execution_id"])
            self.assertEqual(WorkflowRunStore(trace_path).trace_snapshot(run["run_id"])
                             ["invocation"]["runner_run_id"], native_id)
            self.assertTrue(BlockingServer.entered.wait(3))
            self.assertEqual(BlockingServer.turn_starts, 1)
            bridge.cancel(run["run_id"], invocation["invocation_id"],
                          handoff["execution_id"])
        finally:
            adapter.cancel(handoff["execution_id"])

    def test_request_lookup_is_read_only_and_rejects_ambiguous_identity(self):
        base = self.start_http().rsplit("/v1/runs", 1)[0]
        request_id = self.body["request_id"]
        code, missing = self.call(base + "/v1/requests/" + request_id,
                                  method="GET")
        self.assertEqual((code, missing["error_category"]),
                         (404, "request_not_found"))
        self.assertEqual(BlockingServer.turn_starts, 0)
        gate = threading.Event()
        first = self.runner.start_async(self.body, response_gate=gate)
        code, found = self.call(base + "/v1/requests/" + request_id,
                                method="GET")
        self.assertEqual((code, found["run_id"]), (200, first["run_id"]))
        self.assertEqual(BlockingServer.turn_starts, 0)
        body = {key: value for key, value in self.body.items()
                if key != "request_id"}
        self.runner._prepare(body, client_request_id=request_id,
                             request_hash="sha256:synthetic-conflict")
        code, conflict = self.call(base + "/v1/requests/" + request_id,
                                   method="GET")
        self.assertEqual((code, conflict["error_category"]),
                         (409, "request_identity_conflict"))
        self.assertEqual(BlockingServer.turn_starts, 0)
        gate.set()
        self.runner.cancel(first["run_id"])

    def test_cancel_pending_at_ack_is_forwarded_by_adapter(self):
        base = self.start_http()
        class CountingAdapter(RunnerAdapter):
            cancel_calls = 0
            def cancel(self, execution_id):
                self.cancel_calls += 1
                return super().cancel(execution_id)
        adapter = CountingAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                  {"codex": self.state / "api-token"})
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task",
                           skills=[self.body["skill_ref"]])
        cancelled = threading.Event()
        try:
            result = adapter.dispatch(handoff, deadline=time.monotonic() + 5,
                                      cancelled=cancelled, early_start=True,
                                      on_ack=lambda _: cancelled.set())
            self.assertEqual(result["status"], "cancelled")
        except HandoffError as exc:
            # A slow backend may outlive this wait; that is uncertainty, not
            # proof that forwarding Stop failed or that the turn stopped.
            self.assertEqual(str(exc), "runner_result_pending")
        self.assertEqual(adapter.cancel_calls, 1)
        run_id = adapter.active[handoff["execution_id"]][1]
        self.assertEqual(self.runner.status(run_id)["run_id"], run_id)
        deadline = time.monotonic() + 6
        terminal = self.runner.status(run_id)
        while terminal["status"] in {"prepared", "running"} and time.monotonic() < deadline:
            time.sleep(.02)
            terminal = self.runner.status(run_id)
        self.assertIn(terminal["status"], {"cancelled", "timeout"},
                      f"terminal status was {terminal['status']}")
        self.assertLessEqual(BlockingServer.turn_starts, 1)

    def test_poll_deadline_retains_early_identity_and_does_not_cancel(self):
        base = self.start_http()
        adapter = RunnerAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                {"codex": self.state / "api-token"})
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task",
                           skills=[self.body["skill_ref"]])
        acknowledged = []
        with self.assertRaisesRegex(HandoffError, "runner_result_pending"):
            adapter.dispatch(handoff, deadline=time.monotonic() + .3,
                             cancelled=threading.Event(), early_start=True,
                             on_ack=acknowledged.append)
        self.assertEqual(len(acknowledged), 1)
        run_id = acknowledged[0]["run_id"]
        self.assertEqual(adapter.active[handoff["execution_id"]][1], run_id)
        self.assertIn(self.runner.status(run_id)["status"], {"prepared", "running"})
        # Timing out the wait must not silently claim the remote turn stopped.
        self.assertFalse(self.runner.status(run_id)["cancel_confirmed"])
        adapter.cancel(handoff["execution_id"])
        terminal = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            terminal = self.runner.status(run_id)
            if terminal["status"] in {"cancelled", "timeout"}:
                break
            time.sleep(.02)
        self.assertIn(terminal["status"], {"cancelled", "timeout"})
        self.assertEqual(terminal["cancel_confirmed"],
                         terminal["status"] == "cancelled")
        self.assertLessEqual(BlockingServer.turn_starts, 1)

    def test_late_cancel_cannot_overwrite_terminal_record_with_running(self):
        run_id = self.runner.start_async(self.body)["run_id"]
        self.assertTrue(BlockingServer.entered.wait(2))
        write_paused, release = threading.Event(), threading.Event()
        original_json = runner_module._json
        result = {}
        def delayed_json(path, value):
            if (path.name == "record.json" and value.get("status") == "running"
                    and value.get("cancel_requested") and not write_paused.is_set()):
                write_paused.set()
                release.wait(3)
            return original_json(path, value)
        def cancel():
            result["cancel"] = self.runner.cancel(run_id)
        with patch.object(runner_module, "_json", side_effect=delayed_json):
            caller = threading.Thread(target=cancel)
            caller.start()
            try:
                self.assertTrue(write_paused.wait(2))
                # The worker has reached its final write while cancel still
                # holds an older running record. Without the shared lock the
                # late cancel write resurrects that stale running state.
                self.assertTrue(BlockingServer.closed.wait(2))
            finally:
                release.set()
                caller.join(3)
        self.assertFalse(caller.is_alive())
        self.assertTrue(result["cancel"]["cancel_requested"])
        self.assertTrue(self.wait_status(run_id, "cancelled")["cancel_confirmed"])


if __name__ == "__main__":
    unittest.main()
