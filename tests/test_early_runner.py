"""Credential-free falsifiers for issue #22's durable early identity."""

import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from urllib import error as http_error, request as http_request
from uuid import uuid4

from laomedo.local_runner import LocalRunner, RunnerError, _json, serve
from laomedo.handoff_http import RunnerAdapter
from laomedo.handoffs import envelope
from laomedo.skill_store import SkillStore
from tests.test_local_runner import FakeServer


class BlockingServer(FakeServer):
    entered = threading.Event()
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

    def test_cancel_pending_at_ack_is_forwarded_by_adapter(self):
        base = self.start_http()
        adapter = RunnerAdapter({"codex": base.rsplit("/v1/runs", 1)[0]},
                                {"codex": self.state / "api-token"})
        handoff = envelope(None, {"provider": "codex", "model": "test-model",
                                  "effort": "low"}, "Synthetic task",
                           skills=[self.body["skill_ref"]])
        cancelled = threading.Event()
        result = adapter.dispatch(handoff, deadline=time.monotonic() + 5,
                                  cancelled=cancelled, early_start=True,
                                  on_ack=lambda _: cancelled.set())
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(self.runner.status(result["run_id"])["cancel_confirmed"])
        self.assertLessEqual(BlockingServer.turn_starts, 1)


if __name__ == "__main__":
    unittest.main()
