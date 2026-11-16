"""Durable resumed-attempt admission with real SQLite and HTTP control paths."""

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from laomedo.agents.agents.base.resume import ResumeDispatcher
from laomedo.agents.errors import RunnerError
from laomedo.host.runner.http.server import RunnerServer
from support.http_server import RunningHTTPServer
from test_agents.test_runtime.models import RunnerCase


class ResumeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run_id = str(uuid4())
        self.body = {
            "task": "Follow up",
            "activity_attempt_id": str(uuid4()),
            "expected_thread_id": "native-thread",
            "expected_post_run_hash": "sha256:" + "a" * 64,
            "model": "fixture",
            "effort": "low",
        }
        self.runner = Mock(state=Path(self.directory.name), instance_id=str(uuid4()))
        self.runner._mcp_manifest.return_value = None
        self.runner.bind_mcp_resume.return_value = None
        self.runner.prepare_resume.return_value = {}
        self.runner.resume.return_value = {"status": "completed", "answer": "done"}
        self.dispatcher = ResumeDispatcher(self.runner)

    def terminal(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.dispatcher.lookup(
                self.run_id, self.body["activity_attempt_id"]
            )
            if result["status"] not in {"reserved", "running"}:
                return result
            time.sleep(0.01)
        self.fail("resume did not settle")

    def test_duplicate_before_reply_and_after_completion_dispatches_once(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        first = self.dispatcher.submit(self.run_id, self.body, response_gate=gate)
        duplicate = self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(first, duplicate)
        self.runner.bind_mcp_resume.assert_not_called()
        gate.set()
        result = self.terminal()
        self.assertEqual(result["result"]["answer"], "done")
        self.assertEqual(self.dispatcher.submit(self.run_id, self.body), result)
        self.runner.resume.assert_called_once()

    def test_changed_message_and_competing_attempt_refuse_before_mcp(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.dispatcher.submit(self.run_id, self.body, response_gate=gate)
        for changes, code in (
            ({"task": "Different"}, "request_identity_conflict"),
            ({"activity_attempt_id": str(uuid4())}, "resume_already_active"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(RunnerError, code):
                self.dispatcher.submit(self.run_id, {**self.body, **changes})
        self.runner.bind_mcp_resume.assert_not_called()
        gate.set()
        self.terminal()

    def test_transient_registration_changes_do_not_change_identity_or_persist(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        from laomedo.agents.mcp.models import McpManifest, McpTool

        typed = McpManifest(
            tools=(
                McpTool(
                    server="test",
                    upstream_name="read",
                    display_name="Read",
                    description="Read",
                    input_schema={"type": "object"},
                ),
            )
        )
        manifest = typed.model_dump(mode="json")
        self.runner._mcp_manifest.return_value = typed
        first = {
            **self.body,
            "mcp_manifest": manifest,
            "mcp_registration": str(uuid4()),
        }
        second = {**first, "mcp_registration": str(uuid4())}
        self.dispatcher.submit(self.run_id, first, response_gate=gate)
        self.dispatcher.submit(self.run_id, second)
        self.runner.bind_mcp_resume.assert_not_called()
        raw = self.dispatcher.path.read_bytes()
        self.assertNotIn(first["mcp_registration"].encode(), raw)
        self.assertNotIn(second["mcp_registration"].encode(), raw)
        self.assertNotIn(self.body["task"].encode(), raw)
        gate.set()
        self.terminal()

    def test_concurrent_duplicate_submissions_share_one_durable_attempt(self):
        gate, barrier = threading.Event(), threading.Barrier(5)
        self.addCleanup(gate.set)
        results, errors = [], []

        def submit():
            try:
                barrier.wait(timeout=5)
                results.append(
                    ResumeDispatcher(self.runner).submit(
                        self.run_id, self.body, response_gate=gate
                    )
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=submit) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=6)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 5)
        self.assertTrue(all(item == results[0] for item in results))
        gate.set()
        self.terminal()
        self.runner.resume.assert_called_once()

    def test_old_runner_reservation_is_unknown_and_never_replayed(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.dispatcher.submit(self.run_id, self.body, response_gate=gate)
        other = Mock(state=self.runner.state, instance_id=str(uuid4()))
        other._mcp_manifest.return_value = None
        observed = ResumeDispatcher(other).submit(self.run_id, self.body)
        self.assertEqual(observed["status"], "unknown")
        other.bind_mcp_resume.assert_not_called()
        other.resume.assert_not_called()
        gate.set()
        self.terminal()

    def test_native_exception_stays_unknown_and_blocks_next_dispatch(self):
        self.runner.resume.side_effect = RunnerError("container_termination_unverified")
        self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(self.terminal()["status"], "unknown")
        with self.assertRaisesRegex(RunnerError, "resume_already_active"):
            self.dispatcher.submit(
                self.run_id, {**self.body, "activity_attempt_id": str(uuid4())}
            )
        self.runner.resume.assert_called_once()

    def test_completion_is_not_visible_until_owned_grant_release(self):
        entered, finish = threading.Event(), threading.Event()
        access = object()
        self.runner.bind_mcp_resume.return_value = access

        def release(*args, **kwargs):
            entered.set()
            finish.wait(timeout=5)

        self.runner.release_mcp.side_effect = release
        self.addCleanup(finish.set)
        self.dispatcher.submit(self.run_id, self.body)
        self.assertTrue(entered.wait(timeout=5))
        self.assertEqual(
            self.dispatcher.lookup(self.run_id, self.body["activity_attempt_id"])[
                "status"
            ],
            "running",
        )
        finish.set()
        self.assertEqual(self.terminal()["status"], "finished")
        self.runner.release_mcp.assert_called_once_with(self.run_id, expected=access)


class ResumeDispatchHTTPTests(unittest.TestCase):
    def test_real_existing_provider_resume_and_authenticated_lookup(self):
        case = RunnerCase.create()
        self.addCleanup(case.close)
        initial = case.runner.start(case.request())
        body = {
            "task": "Continue",
            "activity_attempt_id": str(uuid4()),
            "expected_thread_id": initial["thread_id"],
            "expected_post_run_hash": initial["post_run_hash"],
            "model": "test-model",
            "effort": "low",
        }
        with patch(
            "laomedo.host.runner.http.server.Settings",
            return_value=SimpleNamespace(startup_gate=""),
        ):
            server = RunnerServer(case.runner, port=0)
        with RunningHTTPServer(server) as running:
            base = f"http://127.0.0.1:{running.server_port}/v1/runs/{initial['run_id']}/resume"
            headers = {
                "Authorization": "Bearer " + case.runner.api_token,
                "Content-Type": "application/json",
            }
            with urlopen(
                Request(
                    base + "/async", data=json.dumps(body).encode(), headers=headers
                ),
                timeout=5,
            ) as response:
                self.assertEqual(response.status, 202)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with urlopen(
                    Request(base + "/" + body["activity_attempt_id"], headers=headers),
                    timeout=5,
                ) as response:
                    observed = json.load(response)
                if observed["status"] not in {"reserved", "running"}:
                    break
                time.sleep(0.01)
            self.assertEqual(observed["status"], "finished", observed)
            self.assertEqual(observed["result"]["thread_id"], initial["thread_id"])
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + "/" + body["activity_attempt_id"], timeout=5)
            self.assertEqual(failure.exception.code, 401)
            failure.exception.close()
