"""Host trace closure controls, with no model, credential or Docker calls."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from laomedo.local_runner import _execution_evidence
import test_local_runner as fixtures


def item(method, identity="answer", kind="agentMessage", **fields):
    return {"method": method, "params": {"threadId": "native-thread", "turnId": "turn-1",
        "item": {"id": identity, "type": kind, **fields}}}


def terminal():
    return {"method": "turn/completed", "params": {"threadId": "native-thread",
        "turn": {"id": "turn-1", "status": "completed"}}}


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "events.jsonl"
        self.record = {"status": "completed", "thread_id": "native-thread", "answer": "done",
            "snapshot_ready": True, "controller_cleanup": "confirmed",
            "container_ownership": {"cleanup_verified": True}}
        self.turns = [{"turn_id": "turn-1", "status": "completed"}]
        self.events = [item("item/started"), item("item/completed", text="done"), terminal()]

    def check(self, events=None, prefix=b"", streams=True):
        self.path.write_bytes(prefix + b"".join(
            (json.dumps(event) + "\n").encode() for event in (self.events if events is None else events)))
        return _execution_evidence(self.path, len(prefix), self.record, self.turns, streams_closed=streams)

    def test_exact_terminal_trace_closes_without_claiming_semantic_success(self):
        result = self.check()
        self.assertIs(result["evidence_complete"], True)
        self.assertEqual(result["completion_basis"], "native_trace_closure")
        self.assertEqual(result["evidence_closure"]["turn_count"], 1)

    def test_completed_answer_alone_or_other_thread_cannot_close(self):
        self.assertEqual(self.check(self.events[:-1])["evidence_complete"], "unknown")
        self.events[-1]["params"]["threadId"] = "other"
        self.assertEqual(self.check()["evidence_complete"], "unknown")

    def test_open_command_or_noncommand_tool_refuses(self):
        for kind in ("commandExecution", "dynamicToolCall", "mcpToolCall", "fileChange"):
            with self.subTest(kind=kind):
                events = [item("item/started", "tool", kind)] + self.events
                self.assertEqual(self.check(events)["evidence_complete"], "unknown")

    def test_closed_command_needs_real_terminal_status_or_integer_exit(self):
        for fields, complete in (({}, False), ({"exitCode": True}, False),
                                 ({"status": "inProgress"}, False), ({"exitCode": 0}, True)):
            with self.subTest(fields=fields):
                events = [item("item/started", "cmd", "commandExecution"),
                          item("item/completed", "cmd", "commandExecution", **fields)] + self.events
                self.assertEqual(self.check(events)["evidence_complete"], True if complete else "unknown")

    def test_duplicate_identity_late_item_and_unbound_item_refuse(self):
        unbound = item("item/completed", text="done")
        del unbound["params"]["turnId"]
        variants = ([self.events[0]] + self.events, self.events + [self.events[0]],
                    self.events + [terminal()], [unbound, terminal()])
        for events in variants:
            self.assertEqual(self.check(events)["evidence_complete"], "unknown")

    def test_cleanup_stream_and_snapshot_unknown_cannot_close(self):
        self.assertEqual(self.check(streams=False)["evidence_complete"], "unknown")
        for key, value in (("status", "cancelled"), ("snapshot_ready", False),
                           ("controller_cleanup", "unverified"), ("answer", "other")):
            old = self.record[key]; self.record[key] = value
            self.assertEqual(self.check()["evidence_complete"], "unknown")
            self.record[key] = old
        self.record["container_ownership"]["cleanup_verified"] = False
        self.assertEqual(self.check()["evidence_complete"], "unknown")

    def test_prior_resume_bytes_do_not_close_new_attempt(self):
        prefix = b"PRIVATE OLD INVALID TRACE\n"
        self.assertIs(self.check(prefix=prefix)["evidence_complete"], True)
        self.assertEqual(self.check(self.events[:-1], prefix=prefix)["evidence_complete"], "unknown")

    def test_unreadable_or_truncated_trace_refuses_without_raw_content(self):
        self.path.write_bytes(b"PRIVATE MALFORMED TRACE\n")
        result = _execution_evidence(self.path, 0, self.record, self.turns, streams_closed=True)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.check()
        self.path.write_bytes(self.path.read_bytes().rstrip(b"\n"))
        self.assertEqual(_execution_evidence(self.path, 0, self.record, self.turns,
                                            streams_closed=True)["evidence_complete"], "unknown")


class RunnerClosureTests(unittest.TestCase):
    setUp = fixtures.LocalRunnerTests.setUp
    tearDown = fixtures.LocalRunnerTests.tearDown
    request = fixtures.LocalRunnerTests.request

    def test_host_closes_and_reopens_exact_trace_after_verified_cleanup(self):
        class ClosedServer(fixtures.FakeServer):
            def __init__(server, *args):
                super().__init__(*args)
                server.reader = SimpleNamespace(is_alive=lambda: False)
                server.stderr_reader = SimpleNamespace(is_alive=lambda: False)
            def wait_turn(server, turn_id, timeout, cancelled):
                (server.evidence / "workspace" / "agent.txt").write_text("from-first-turn")
                server.events = [item("item/started"), item("item/completed", text="done"), terminal()]
                for event in server.events:
                    server.log.write(json.dumps(event) + "\n")
                server.log.flush()
                return "completed", None
        self.runner.transport = ClosedServer
        self.runner.supervise_containers = True
        self.runner.lease_service = self.root / "dummy-lease"
        lease = SimpleNamespace(lost=threading.Event(), finish=lambda: None,
                                instance="fixture-service", grant_id=None)
        with patch("laomedo.local_runner.LeaseClient", return_value=lease), \
                patch("laomedo.local_runner.cleanup_exact", return_value=(True, "absent")):
            result = self.runner.start(self.request())
        self.assertEqual(result["status"], "completed", result.get("error_category"))
        self.assertIs(result["evidence_complete"], True)
        reopened = self.runner.status(result["run_id"])
        self.assertEqual(reopened["evidence_closure"], result["evidence_closure"])


if __name__ == "__main__":
    unittest.main()
