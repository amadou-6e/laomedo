"""Credential-free runner and pinned-skill contract tests."""

from pathlib import Path
import json
import tempfile
import threading
import unittest
from urllib import request as http_request, error as http_error

from laomedo.local_runner import AppServer, LocalRunner, RunnerError, _hash_tree, serve
from laomedo.skill_store import SkillStore


class FakeServer:
    calls = []

    def __init__(self, command, evidence):
        self.command = command
        self.evidence = evidence
        self.events = []
        self.resume = False
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
        self.log.write('{"method":"initialized"}\n')
        self.log.flush()
        self.calls.append(command)

    def request(self, method, params, timeout=30):
        if method == "initialize":
            return {"result": {}}
        if method == "model/list":
            return {"result": {"data": [{"id": "test-model",
                "supportedReasoningEfforts": ["low"]}]}}
        if method == "thread/start":
            return {"result": {"thread": {"id": "native-thread"}}}
        if method == "thread/resume":
            self.resume = True
            assert params["threadId"] == "native-thread"
            return {"result": {"thread": {"id": "native-thread"}}}
        if method == "turn/start":
            return {"result": {"turn": {"id": "turn-2" if self.resume else "turn-1"}}}
        raise AssertionError(method)

    def notify(self, method, params):
        pass

    def wait_turn(self, turn_id, timeout, cancelled):
        workspace = self.evidence / "workspace"
        if self.resume:
            assert (workspace / "agent.txt").read_text() == "from-first-turn"
        else:
            assert not (workspace / "agent.txt").exists()
            (workspace / "agent.txt").write_text("from-first-turn")
        self.events.append({"method": "item/completed", "params": {"item": {
            "type": "agentMessage", "text": "synthetic answer"}}})
        self.log.write('{"method":"turn/completed"}\n')
        self.log.flush()
        return "completed", None

    def close(self):
        self.log.close()


class LocalRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "task.txt").write_text("source input")
        (self.root / ".git").mkdir()
        self.skill_source = self.root / "skill-source"
        self.skill_source.mkdir()
        (self.skill_source / "SKILL.md").write_text("---\nname: sample\n---\nUse amber.\n")
        store = SkillStore(self.root.parent / (self.root.name + "-skill-store"))
        self.addCleanup(lambda: __import__("shutil").rmtree(store.root.parent /
                        (self.root.name + "-skill-store"), ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(store.draft_root,
                        ignore_errors=True))
        self.revision = store.import_skill("sample", self.skill_source)
        self.runner = LocalRunner(self.root.parent / (self.root.name + "-state"),
                                  store.root, self.source, transport=FakeServer,
                                  check_docker=False, max_model_turns=6)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.runner.state,
                        ignore_errors=True))

    def request(self):
        return {"task": "Use the sample skill", "model": "test-model",
                "effort": "low",
                "skill_ref": {"skill_id": "sample",
                              "revision_id": self.revision["revision_id"],
                              "tree_hash": self.revision["tree_hash"]}}

    def test_start_resume_and_fresh_workspace(self):
        first = self.runner.start(self.request())
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["thread_id"], "native-thread")
        self.assertEqual(first["skill"]["use_evidence"], "offered")
        self.assertEqual(first["answer"], "synthetic answer")
        command = FakeServer.calls[-1]
        self.assertIn("type=volume,source=laomedo-122-docker-auth,target=/home/runner/.codex",
                      command)
        self.assertNotIn("auth.json", " ".join(command))
        output = self.runner._run_dir(first["run_id"]) / "post-run"
        self.assertEqual(_hash_tree(output), first["post_run_hash"])
        self.assertFalse((self.source / "agent.txt").exists())
        self.assertEqual((output / ".agents/skills/sample/SKILL.md").read_text(),
                         (self.skill_source / "SKILL.md").read_text())
        second = self.runner.start(self.request())
        self.assertNotEqual(second["run_id"], first["run_id"])
        restarted = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                                 transport=FakeServer, check_docker=False,
                                 max_model_turns=6)
        resumed = restarted.resume(first["run_id"], "continue",
                                   expected_post_run_hash=first["post_run_hash"],
                                   expected_thread_id=first["thread_id"],
                                   model="test-model", effort="low")
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(len(resumed["turns"]), 2)
        self.assertEqual(json.loads((self.runner.state / "turn-ledger.json").read_text())
                         ["attempted_turns"], 3)

    def test_multiple_skills_materialize_and_resume_as_one_bound_snapshot(self):
        second = self.runner.store.import_skill("second", self.skill_source)
        request = self.request()
        first_ref = request.pop("skill_ref")
        request["skill_refs"] = [first_ref, {"skill_id": "second",
            "revision_id": second["revision_id"], "tree_hash": second["tree_hash"]}]
        result = self.runner.start(request)
        self.assertEqual([s["skill_id"] for s in result["skills"]], ["sample", "second"])
        self.assertIsNone(result["skill"])
        for name in ("sample", "second"):
            self.assertTrue((self.runner._run_dir(result["run_id"]) /
                             "post-run/.agents/skills" / name / "SKILL.md").is_file())
        resumed = self.runner.resume(result["run_id"], "continue",
            expected_post_run_hash=result["post_run_hash"],
            expected_thread_id=result["thread_id"], model="test-model", effort="low")
        self.assertEqual(resumed["skills"], result["skills"])

    def test_multiple_skill_failure_cleans_partial_materialization_without_dispatch(self):
        request = self.request()
        ref = request.pop("skill_ref")
        before = len(FakeServer.calls)
        request["skill_refs"] = [ref, {**ref, "skill_id": "missing"}]
        with self.assertRaises(Exception):
            self.runner.start(request)
        self.assertEqual(len(FakeServer.calls), before)
        self.assertEqual(list((self.runner.state / "runs").iterdir()), [])
        request["skill_refs"] = [ref, ref]
        with self.assertRaisesRegex(RunnerError, "duplicate_skill_id"):
            self.runner.start(request)

    def test_default_turn_cap_denies_model_submission(self):
        stopped = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                              transport=FakeServer, check_docker=False)
        result = stopped.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "model_turn_cap_reached")
        self.assertIsNone(result["answer"])

    def test_restart_marks_incomplete_run_interrupted_without_losing_trace(self):
        first = self.runner.start(self.request())
        run_dir = self.runner._run_dir(first["run_id"])
        record = json.loads((run_dir / "record.json").read_text())
        record["status"] = "running"
        (run_dir / "record.json").write_text(json.dumps(record))
        before = (run_dir / "raw-events.jsonl").read_bytes()
        restarted = LocalRunner(self.runner.state, self.runner.store.root, self.source,
                                 transport=FakeServer, check_docker=False)
        after = restarted.status(first["run_id"])
        self.assertEqual(after["status"], "interrupted")
        self.assertEqual(after["error_category"], "runner_restarted")
        self.assertEqual((run_dir / "raw-events.jsonl").read_bytes(), before)

    def test_missing_or_changed_snapshot_refused(self):
        first = self.runner.start(self.request())
        args = dict(expected_post_run_hash=first["post_run_hash"],
                    expected_thread_id=first["thread_id"], model="test-model", effort="low")
        with self.assertRaisesRegex(RunnerError, "resume_binding_mismatch"):
            self.runner.resume(first["run_id"], "continue", **{**args, "model": "other"})
        (self.runner._run_dir(first["run_id"]) / "post-run/task.txt").write_text("tampered")
        with self.assertRaisesRegex(RunnerError, "post_run_snapshot_mismatch"):
            self.runner.resume(first["run_id"], "continue", **args)

    def test_missing_post_run_snapshot_refused(self):
        first = self.runner.start(self.request())
        snapshot = self.runner._run_dir(first["run_id"]) / "post-run"
        __import__("shutil").rmtree(snapshot)
        with self.assertRaisesRegex(RunnerError, "post_run_snapshot_mismatch"):
            self.runner.resume(first["run_id"], "continue",
                               expected_post_run_hash=first["post_run_hash"],
                               expected_thread_id=first["thread_id"],
                               model="test-model", effort="low")

    def test_empty_directory_change_invalidates_workspace_hash(self):
        first = self.runner.start(self.request())
        snapshot = self.runner._run_dir(first["run_id"]) / "post-run"
        (snapshot / "new-empty-directory").mkdir()
        self.assertNotEqual(_hash_tree(snapshot), first["post_run_hash"])

    def test_changed_canonical_mount_refuses_resume(self):
        first = self.runner.start(self.request())
        canonical = self.runner._run_dir(first["run_id"]) / "canonical/task.txt"
        canonical.write_text("changed")
        with self.assertRaisesRegex(RunnerError, "protected_mount_changed"):
            self.runner.resume(first["run_id"], "continue",
                               expected_post_run_hash=first["post_run_hash"],
                               expected_thread_id=first["thread_id"],
                               model="test-model", effort="low")

    def test_missing_and_changed_skill_revision_fail_before_turn(self):
        original = self.runner.start(self.request())
        delivered = (self.runner._run_dir(original["run_id"]) /
                     "post-run/.agents/skills/sample/SKILL.md").read_bytes()
        request = self.request()
        request["skill_ref"]["revision_id"] = "sha256:" + "0" * 64
        with self.assertRaises(RunnerError):
            self.runner.start(request)
        request = self.request()
        bundle = self.runner.store._revision_dir("sample", self.revision["revision_id"]) / "bundle"
        (bundle / "SKILL.md").write_text("tampered")
        with self.assertRaises(Exception):
            self.runner.start(request)
        self.assertEqual((self.runner._run_dir(original["run_id"]) /
                          "post-run/.agents/skills/sample/SKILL.md").read_bytes(), delivered)

    def test_skill_path_escape_refused(self):
        request = self.request()
        request["skill_ref"]["skill_id"] = "../outside"
        with self.assertRaises(Exception):
            self.runner.start(request)

    def test_http_start_and_status_keep_private_paths_out(self):
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        base = f"http://127.0.0.1:{server.server_port}/v1/runs"
        request = http_request.Request(base, data=json.dumps(self.request()).encode(),
                                       headers={"Content-Type": "application/json"})
        with http_request.urlopen(request) as response:
            result = json.load(response)
        with http_request.urlopen(base + "/" + result["run_id"]) as response:
            status = json.load(response)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["raw_event_ref"],
                         f"laomedo:run:{result['run_id']}:events")
        self.assertNotIn(str(self.root), json.dumps(status))

    def test_http_rejects_simple_cross_origin_content_type(self):
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        req = http_request.Request(f"http://127.0.0.1:{server.server_port}/v1/runs",
                                   data=json.dumps(self.request()).encode(),
                                   headers={"Content-Type": "text/plain"})
        with self.assertRaises(http_error.HTTPError) as caught:
            http_request.urlopen(req)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)["error_category"],
                         "json_content_type_required")

    def test_http_failure_preserves_run_id_and_partial_events(self):
        class TimedOut(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                self.log.write('{"method":"item/started"}\n')
                self.log.flush()
                return "timeout", "turn_timeout"

        self.runner.transport = TimedOut
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        req = http_request.Request(f"http://127.0.0.1:{server.server_port}/v1/runs",
                                   data=json.dumps(self.request()).encode(),
                                   headers={"Content-Type": "application/json"})
        with self.assertRaises(http_error.HTTPError) as caught:
            http_request.urlopen(req)
        self.assertEqual(caught.exception.code, 502)
        result = json.load(caught.exception)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["error_category"], "turn_timeout")
        self.assertIsNone(result["answer"])
        self.assertIn("item/started", (self.runner._run_dir(result["run_id"]) /
                                       "raw-events.jsonl").read_text())

    def test_http_cancel_marks_running_turn_and_retains_partial_events(self):
        started = threading.Event()

        class Blocking(FakeServer):
            def wait_turn(self, turn_id, timeout, cancelled):
                self.log.write('{"method":"item/started"}\n')
                self.log.flush()
                started.set()
                assert cancelled.wait(3)
                return "cancelled", "cancelled_by_user"

        self.runner.transport = Blocking
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        base = f"http://127.0.0.1:{server.server_port}/v1/runs"
        result = {}

        def submit():
            req = http_request.Request(base, data=json.dumps(self.request()).encode(),
                                       headers={"Content-Type": "application/json"})
            try:
                http_request.urlopen(req)
            except http_error.HTTPError as exc:
                result.update(json.load(exc))

        submitting = threading.Thread(target=submit)
        submitting.start()
        self.assertTrue(started.wait(2))
        run_dir = next((self.runner.state / "runs").iterdir())
        req = http_request.Request(base + "/" + run_dir.name + "/cancel",
                                   data=b"{}", method="POST",
                                   headers={"Content-Type": "application/json"})
        with http_request.urlopen(req) as response:
            self.assertEqual(response.status, 202)
            self.assertTrue(json.load(response)["cancel_requested"])
        submitting.join(3)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["run_id"], run_dir.name)
        self.assertIn("item/started", (run_dir / "raw-events.jsonl").read_text())

    def test_completion_queued_before_turn_start_response_is_observed(self):
        server = AppServer.__new__(AppServer)
        server.events = [{"method": "turn/completed", "params": {"turn": {
            "id": "fast-turn", "status": "completed"}}}]
        status, error = server.wait_turn("fast-turn", .1, threading.Event())
        self.assertEqual((status, error), ("completed", None))


if __name__ == "__main__":
    unittest.main()
