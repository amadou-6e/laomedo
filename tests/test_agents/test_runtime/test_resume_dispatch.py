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
        self.runner.status.return_value = {
            "status": "completed",
            "thread_id": "native-thread",
            "activity_attempt_id": str(uuid4()),
            "attempt_finished": True,
            "controller_cleanup": "confirmed",
            "container_ownership": {"cleanup_verified": True},
        }
        self.runner.mcp_access.return_value = None
        self.runner.lock = threading.Lock()
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
        self.assertEqual(self.dispatcher.pending(), [])
        self.assertFalse(self.dispatcher.path.exists())
        first = self.dispatcher.submit(self.run_id, self.body, response_gate=gate)
        self.assertEqual(
            [item["run_id"] for item in self.dispatcher.pending()], [self.run_id]
        )
        duplicate = self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(first, duplicate)
        self.runner.bind_mcp_resume.assert_not_called()
        gate.set()
        result = self.terminal()
        self.assertEqual(result["result"]["status"], "completed")
        self.assertEqual(self.dispatcher.pending(), [])
        self.assertNotIn("answer", result["result"])
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
        def fail_after_dispatch(*args, **kwargs):
            self.runner.status.return_value = {
                "status": "running",
                "activity_attempt_id": kwargs["activity_attempt_id"],
                "attempt_finished": False,
            }
            raise RunnerError("container_termination_unverified")

        self.runner.resume.side_effect = fail_after_dispatch
        self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(self.terminal()["status"], "unknown")
        with self.assertRaisesRegex(RunnerError, "resume_already_active"):
            self.dispatcher.submit(
                self.run_id, {**self.body, "activity_attempt_id": str(uuid4())}
            )
        self.runner.resume.assert_called_once()

    def test_definite_refusal_leaves_next_attempt_dispatchable(self):
        self.runner.resume.side_effect = RunnerError("resume_binding_mismatch")
        self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(self.terminal()["status"], "failed")
        self.runner.resume.side_effect = None
        self.body = {**self.body, "activity_attempt_id": str(uuid4())}
        self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(self.terminal()["status"], "finished")
        self.assertEqual(self.runner.resume.call_count, 2)

    def test_reconcile_requires_matching_terminal_attempt_and_verified_cleanup(self):
        with self.dispatcher._connection() as connection:
            connection.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,?,NULL,NULL)",
                (
                    self.run_id,
                    self.body["activity_attempt_id"],
                    "digest",
                    "old-instance",
                    "running",
                    None,
                ),
            )
        self.assertEqual(self.dispatcher.pending()[0]["status"], "unknown")
        observed = self.dispatcher.lookup(self.run_id, self.body["activity_attempt_id"])
        self.assertEqual(observed["status"], "unknown")
        self.runner.status.return_value["activity_attempt_id"] = self.body[
            "activity_attempt_id"
        ]
        self.runner.status.return_value["container_ownership"][
            "cleanup_verified"
        ] = False
        self.assertEqual(
            self.dispatcher.lookup(self.run_id, self.body["activity_attempt_id"])[
                "status"
            ],
            "unknown",
        )
        self.runner.status.return_value["container_ownership"][
            "cleanup_verified"
        ] = True
        self.assertEqual(self.dispatcher.pending(), [])
        observed = self.dispatcher.lookup(self.run_id, self.body["activity_attempt_id"])
        self.assertEqual(observed["status"], "finished")
        self.assertEqual(observed["result"]["status"], "completed")
        self.runner.resume.assert_not_called()

    def test_synchronous_and_asynchronous_admission_exclude_each_other(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        with self.dispatcher.synchronous(self.run_id):
            with self.assertRaisesRegex(RunnerError, "resume_already_active"):
                self.dispatcher.submit(self.run_id, self.body)
        self.dispatcher.submit(self.run_id, self.body, response_gate=gate)
        with self.assertRaisesRegex(RunnerError, "resume_already_active"):
            with self.dispatcher.synchronous(self.run_id):
                self.fail("synchronous resume admitted competing work")
        gate.set()
        self.terminal()

    def test_worker_start_failure_is_durable_and_never_calls_provider(self):
        with patch(
            "laomedo.agents.agents.base.resume.threading.Thread.start",
            side_effect=RuntimeError("private detail"),
        ):
            with self.assertRaisesRegex(RunnerError, "runner_runtime_unknown"):
                self.dispatcher.submit(self.run_id, self.body)
        self.assertEqual(
            self.dispatcher.lookup(self.run_id, self.body["activity_attempt_id"])[
                "status"
            ],
            "failed",
        )
        self.runner.resume.assert_not_called()

    def test_failed_final_write_reconciles_after_storage_recovers(self):
        completed = threading.Event()

        def completed_resume(*args, **kwargs):
            self.runner.status.return_value["activity_attempt_id"] = kwargs[
                "activity_attempt_id"
            ]
            return dict(self.runner.status.return_value)

        def failed_write(*args, **kwargs):
            completed.set()
            raise RunnerError("resume_journal_unavailable")

        self.runner.resume.side_effect = completed_resume
        with patch.object(self.dispatcher, "_finish", side_effect=failed_write):
            self.dispatcher.submit(self.run_id, self.body)
            self.assertTrue(completed.wait(timeout=5))
        self.assertEqual(self.terminal()["status"], "finished")
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
                if observed["status"] in {"finished", "failed"}:
                    break
                time.sleep(0.01)
            self.assertEqual(observed["status"], "finished", observed)
            self.assertEqual(observed["result"]["thread_id"], initial["thread_id"])
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + "/" + body["activity_attempt_id"], timeout=5)
            self.assertEqual(failure.exception.code, 401)
            failure.exception.close()

    def test_real_provider_stale_hash_refusal_does_not_brick_follow_up(self):
        case = RunnerCase.create()
        self.addCleanup(case.close)
        initial = case.runner.start(case.request())
        body = {
            "task": "Continue",
            "activity_attempt_id": str(uuid4()),
            "expected_thread_id": initial["thread_id"],
            "expected_post_run_hash": "sha256:" + "0" * 64,
            "model": "test-model",
            "effort": "low",
        }
        dispatcher = ResumeDispatcher(case.runner)
        dispatcher.submit(initial["run_id"], body)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            observed = dispatcher.lookup(initial["run_id"], body["activity_attempt_id"])
            if observed["status"] in {"finished", "failed"}:
                break
            time.sleep(0.01)
        self.assertEqual(observed["status"], "failed", observed)
        self.assertEqual(observed["error_category"], "resume_binding_mismatch")
        body.update(
            activity_attempt_id=str(uuid4()),
            expected_post_run_hash=initial["post_run_hash"],
        )
        dispatcher.submit(initial["run_id"], body)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            observed = dispatcher.lookup(initial["run_id"], body["activity_attempt_id"])
            if observed["status"] in {"finished", "failed"}:
                break
            time.sleep(0.01)
        self.assertEqual(observed["status"], "finished", observed)
