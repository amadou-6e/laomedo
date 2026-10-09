"""Credential-free checks for the pre-thread response hold."""

import threading
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from experiments.exp22 import phase_f_prethread
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    phase_f_prethread = None


@unittest.skipUnless(phase_f_prethread is not None,
                     "experiment source is not installed in the wheel")
class PhaseFHoldTests(unittest.TestCase):
    def test_prepared_async_ack_waits_until_released(self):
        replies = []

        class Handler:
            def _reply(self, code, value):
                replies.append((code, value))

        server = mock.Mock(RequestHandlerClass=Handler)
        release = threading.Event()
        waiting = phase_f_prethread._hold_async_ack(server, mock.Mock(), release)
        handler = object.__new__(server.RequestHandlerClass)
        handler.command = "POST"
        handler.path = "/v1/runs/async"
        worker = threading.Thread(target=handler._reply,
                                  args=(202, {"status": "prepared", "run_id": "run-a"}))
        worker.start()
        self.assertTrue(waiting.wait(timeout=1))
        self.assertEqual(replies, [])
        release.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(replies), 1)

    def test_other_routes_are_not_held(self):
        replies = []

        class Handler:
            def _reply(self, code, value):
                replies.append(code)

        server = mock.Mock(RequestHandlerClass=Handler)
        waiting = phase_f_prethread._hold_async_ack(server, mock.Mock(), threading.Event())
        handler = object.__new__(server.RequestHandlerClass)
        handler.command = "POST"
        handler.path = "/v1/runs/run-a/cancel"
        handler._reply(200, {"status": "cancelled"})
        self.assertFalse(waiting.is_set())
        self.assertEqual(replies, [200])

    def test_teardown_cancels_all_records_before_opening_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory) / "runs"
            record = runs / "late-run" / "record.json"
            record.parent.mkdir(parents=True)
            record.write_text("{}", encoding="utf-8")
            runner = mock.Mock()
            runner.request_lock = threading.Lock()
            runner.status.return_value = {"status": "prepared"}
            closing = phase_f_prethread._fence_starts(runner)
            release = threading.Event()
            cleaned = [{"terminal_status": "cancelled", "exact_cleanup_verified": True}]
            with mock.patch.object(phase_f_prethread, "_cleanup_runner_runs",
                                   return_value=cleaned) as cleanup:
                safe, fallback, _ = phase_f_prethread._fence_cancel_and_release(
                    runner, closing, release, runs)
            self.assertTrue(safe)
            self.assertTrue(fallback)
            self.assertTrue(release.is_set())
            cleanup.assert_called_once_with(runner, runs, None)
            with self.assertRaisesRegex(phase_f_prethread.RunnerError, "probe_stopping"):
                runner.start_async({})

    def test_unverified_cleanup_keeps_worker_gate_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory) / "runs"
            record = runs / "late-run" / "record.json"
            record.parent.mkdir(parents=True)
            record.write_text("{}", encoding="utf-8")
            runner = mock.Mock()
            runner.request_lock = threading.Lock()
            runner.status.return_value = {"status": "prepared"}
            closing = phase_f_prethread._fence_starts(runner)
            release = threading.Event()
            cleaned = [{"terminal_status": "running", "exact_cleanup_verified": False}]
            with mock.patch.object(phase_f_prethread, "_cleanup_runner_runs",
                                   return_value=cleaned):
                safe, _, _ = phase_f_prethread._fence_cancel_and_release(
                    runner, closing, release, runs)
            self.assertFalse(safe)
            self.assertFalse(release.is_set())


if __name__ == "__main__":
    unittest.main()
