"""Recovered internal controls; no live Docker or model acceptance is inferred."""

from importlib.util import find_spec
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.claude.container import CommandService


class ProviderRecoveryTests(unittest.TestCase):
    def test_claude_output_limit_survives_the_tool_http_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Mock()
            runtime.job.side_effect = RunnerError("workspace_command_output_too_large")
            service = CommandService(
                runtime,
                Path(temporary),
                {"run_id": "internal-run"},
                threading.Event(),
                time.monotonic() + 10,
            )
            self.addCleanup(service.close)
            with self.assertRaisesRegex(
                RunnerError, "workspace_command_output_too_large"
            ):
                service.execute({"command": "pwd"})
            self.assertEqual(service.error_code, "workspace_command_output_too_large")
            self.assertFalse(service.cleanup_failed)
            runtime.lease.return_value.finish.assert_called_once()

    def test_claude_close_signals_the_active_job_before_returning(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Mock()
            entered = threading.Event()

            def run_job(spec, *, timeout, cancelled):
                entered.set()
                if not cancelled.wait(3):
                    raise AssertionError("Job never received its cancellation signal")
                raise RunnerError("claude_cancelled")

            runtime.job.side_effect = run_job
            service = CommandService(
                runtime,
                Path(temporary),
                {"run_id": "internal-cancel"},
                threading.Event(),
                time.monotonic() + 10,
            )
            outcome = {}

            def command():
                try:
                    service.execute({"command": "pwd"})
                except RunnerError as error:
                    outcome["code"] = str(error)

            worker = threading.Thread(target=command)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                service.close()
            finally:
                service.stopping.set()
                worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcome["code"], "claude_cancelled")
            self.assertFalse(service.cleanup_failed)
            runtime.lease.return_value.finish.assert_called_once()

    def test_claude_pre_dispatch_timeout_does_not_claim_uncertain_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Mock()
            runtime.guarded.side_effect = RunnerError("claude_turn_timeout")
            service = CommandService(
                runtime,
                Path(temporary),
                {"run_id": "internal-deadline"},
                threading.Event(),
                time.monotonic() + 10,
            )
            self.addCleanup(service.close)
            with self.assertRaisesRegex(RunnerError, "claude_turn_timeout"):
                service.execute({"command": "pwd"})
            runtime.job.assert_not_called()
            runtime.lease.return_value.finish.assert_called_once()
            self.assertFalse(service.cleanup_failed)
