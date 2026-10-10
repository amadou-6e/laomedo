"""Native completion is not command completion. No model or Docker needed."""
import json
import unittest

from laomedo.local_runner import _command_summary, AppServer, SplitAppServer, LocalRunner, RunnerError
import threading
from types import SimpleNamespace
from laomedo.artifacts import ArtifactError
import test_local_runner as fixtures


def command(method, identity="exec-1", **fields):
    return {"method": method, "params": {"turnId": "turn-1", "item": {
        "type": "commandExecution", "id": identity, **fields}}}


class ProjectionTests(unittest.TestCase):
    def test_both_native_transports_complete_with_a_dangling_command(self):
        for transport in (AppServer, SplitAppServer):
            events = [command("item/started"), {"method": "turn/completed", "params": {
                "turn": {"id": "turn-1", "status": "completed"}}}]
            server = SimpleNamespace(events=events)
            self.assertEqual(transport.wait_turn(server, "turn-1", 1, threading.Event()),
                             ("completed", None))
            self.assertEqual(_command_summary(events, "turn-1")["outstanding_ids"], ["exec-1"])

    def test_other_turn_and_partial_output(self):
        events = [command("item/started"), {"method": "item/commandExecution/outputDelta",
            "params": {"turnId": "turn-1", "itemId": "exec-1", "delta": "PRIVATE OUTPUT"}},
            {"method": "item/completed", "params": {"turnId": "other", "item": {
                "id": "exec-1", "type": "commandExecution", "exitCode": 0}}}]
        result = _command_summary(events, "turn-1")
        self.assertEqual(result["outstanding_ids"], ["exec-1"])
        self.assertEqual(result["commands"][0]["output_event_indices"], [1])
        self.assertNotIn("PRIVATE OUTPUT", json.dumps(result))

    def test_missing_identity_and_in_progress_completion_stay_unknown(self):
        for events in ([command("item/started", identity=None)],
                       [command("item/started"), command("item/completed", status="inProgress")]):
            result = _command_summary(events, "turn-1")
            self.assertTrue(result["identity_incomplete"] or result["outstanding_ids"])


class RunnerTests(unittest.TestCase):
    setUp = fixtures.LocalRunnerTests.setUp
    tearDown = fixtures.LocalRunnerTests.tearDown
    request = fixtures.LocalRunnerTests.request

    def run_commands(self, events, *, resume=False):
        class Transport(fixtures.FakeServer):
            def wait_turn(server, turn_id, timeout, cancelled):
                status = super().wait_turn(turn_id, timeout, cancelled)
                server.events.extend(events)
                for event in events:
                    server.log.write(json.dumps(event) + "\n")
                server.log.flush()
                return status
        self.runner.transport = Transport
        return self.runner.start(self.request())

    def test_dangling_command_blocks_artifacts_and_retains_evidence_after_restart(self):
        result = self.run_commands([command("item/started")])
        self.assertEqual(result["native_turn_status"], "completed")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["error_category"], "outstanding_command_completion_unknown")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["native_answer"], "synthetic answer")
        self.assertFalse(result["snapshot_ready"])
        self.assertIsNone(result["post_run_hash"])
        root = self.runner._run_dir(result["run_id"])
        self.assertFalse((root / "post-run").exists())
        self.assertIn("exec-1", (root / "raw-events.jsonl").read_text())
        restarted = LocalRunner(self.runner.state, self.runner.store.root, self.source,
            transport=fixtures.FakeServer, check_docker=False, max_model_turns=6)
        self.assertEqual(restarted.status(result["run_id"])["command_summary"]["outstanding_ids"], ["exec-1"])
        self.assertEqual(result["controller_cleanup"], "confirmed")
        with self.assertRaises(ArtifactError):
            self.runner.select_artifacts(result["run_id"], ["agent.txt"])
        with self.assertRaises(RunnerError):
            self.runner.resume(result["run_id"], "continue", expected_post_run_hash="sha256:" + "0" * 64,
                expected_thread_id="native-thread", model="test-model", effort="low")

    def test_explicit_success_allows_snapshot(self):
        result = self.run_commands([command("item/started"),
            command("item/completed", status="completed", exitCode=0)])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["snapshot_ready"])
        self.assertEqual(result["command_summary"]["outstanding_ids"], [])
        self.assertEqual(len(self.runner.select_artifacts(result["run_id"], ["agent.txt"])), 1)

    def test_explicit_failure_or_cancellation_is_terminal_not_task_success(self):
        for status, code in (("failed", 1), ("cancelled", None), ("declined", None)):
            with self.subTest(status=status):
                result = self.run_commands([command("item/started"),
                    command("item/completed", status=status, exitCode=code)])
                self.assertEqual(result["status"], "completed")
                self.assertTrue(result["snapshot_ready"])
                self.assertEqual(result["command_summary"]["outstanding_ids"], [])
                self.assertEqual(result["command_summary"]["commands"][0]["status"], status)

    def test_one_finished_command_does_not_cover_another(self):
        result = self.run_commands([command("item/started"), command("item/started", "exec-2"),
            command("item/completed", status="completed", exitCode=0)])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["command_summary"]["outstanding_ids"], ["exec-2"])

    def test_unknown_command_identity_refuses_readiness(self):
        result = self.run_commands([command("item/completed", identity=None, exitCode=0)])
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["command_summary"]["identity_incomplete"])
        self.assertFalse(result["snapshot_ready"])

    def test_cleanup_failure_does_not_turn_a_dangling_command_into_cancellation(self):
        class Transport(fixtures.FakeServer):
            def wait_turn(server, turn_id, timeout, cancelled):
                super().wait_turn(turn_id, timeout, cancelled)
                server.events.append(command("item/started"))
                return "completed", None
            def close(server):
                super().close()
                raise OSError("synthetic cleanup failure")
        self.runner.transport = Transport
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "container_termination_unverified")
        self.assertEqual(result["controller_cleanup"], "unverified")
        self.assertEqual(result["command_summary"]["commands"][0]["status"], "unknown")
        self.assertFalse(result["snapshot_ready"])

    def test_resume_dangling_command_cannot_reuse_previous_artifact_identity(self):
        first = self.runner.start(self.request())
        class Transport(fixtures.FakeServer):
            def wait_turn(server, turn_id, timeout, cancelled):
                super().wait_turn(turn_id, timeout, cancelled)
                event = command("item/started")
                event["params"]["turnId"] = turn_id
                server.events.append(event)
                return "completed", None
        self.runner.transport = Transport
        result = self.runner.resume(first["run_id"], "continue",
            expected_post_run_hash=first["post_run_hash"],
            expected_thread_id=first["thread_id"], model="test-model", effort="low")
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["output_ref"])
        self.assertIsNone(result["post_run_hash"])
        self.assertFalse(result["snapshot_ready"])
        self.assertTrue((self.runner._run_dir(first["run_id"]) / "post-run").exists())
        with self.assertRaises(ArtifactError):
            self.runner.select_artifacts(first["run_id"], ["agent.txt"])
