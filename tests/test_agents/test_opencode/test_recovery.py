"""Recovered internal controls; no live Docker or model acceptance is inferred."""

from laomedo.agents.agents.base.models.commands import CommandRequest

from importlib.util import find_spec
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.agents.opencode.executor import OpenCodeCommandExecutor
from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime


class ProviderRecoveryTests(unittest.TestCase):
    @unittest.skipUnless(
        find_spec("py_docker"),
        "Requires the optional Docker runtime; covered by docker-runtime-controls",
    )
    def test_previous_catalogue_receipt_is_recovered_or_preserved(self):
        from py_docker.errors import CleanupUnconfirmedError

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            receipt = state.joinpath("catalog/earlier/docker-receipts/controller.json")
            receipt.parent.mkdir(parents=True)
            receipt.write_text("private test intent", encoding="utf-8")
            runner = OpenCodeAgent.__new__(OpenCodeAgent)
            runner.state, runner.transport_factory, runner.lock = (
                state,
                object(),
                threading.Lock(),
            )
            with patch("py_docker.Client") as client:
                recover = client.return_value.__enter__.return_value.sessions.recover
                recover.side_effect = CleanupUnconfirmedError("internal mismatch")
                with self.assertRaisesRegex(
                    RunnerError, "opencode_container_cleanup_unverified"
                ):
                    runner._recover_containers()
                recover.assert_called_once_with(receipt)
            self.assertTrue(receipt.exists())

    def test_catalogue_factory_failure_retains_pending_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = OpenCodeAgent.__new__(OpenCodeAgent)
            runner.state, runner.lock = Path(temporary), threading.Lock()
            runner.catalog._lock = threading.Lock()
            runner.catalog._cached = None

            def fail_after_intent(workspace, evidence):
                receipt = evidence.joinpath("docker-receipts/pending.json")
                receipt.parent.mkdir()
                receipt.write_text("private test intent", encoding="utf-8")
                raise RunnerError("opencode_controller_startup_failed")

            runner.transport_factory = fail_after_intent
            with self.assertRaisesRegex(
                RunnerError, "opencode_controller_startup_failed"
            ):
                runner.model_catalog()
            self.assertEqual(
                len(list(runner.state.glob("catalog/*/docker-receipts/*.json"))), 1
            )
            self.assertFalse(runner.lock.locked())

    @unittest.skipUnless(
        find_spec("py_docker"),
        "Requires the optional Docker runtime; covered by docker-runtime-controls",
    )
    def test_opencode_output_limit_is_a_fatal_run_code(self):
        from py_docker.errors import OutputLimitError

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broker = OpenCodeCommandExecutor(
                root, root, root, root, docker_endpoint="unix:///internal.sock"
            )
            self.addCleanup(broker.shutdown)
            with patch("py_docker.Client") as client:
                client.return_value.__enter__.return_value.jobs.run.side_effect = (
                    OutputLimitError("internal limit")
                )
                self.assertEqual(
                    broker.execute(CommandRequest(command="pwd")).model_dump(
                        exclude={"cleanup"}
                    )["exit_code"],
                    125,
                )
            backend = OpenCodeAgentRuntime.__new__(OpenCodeAgentRuntime)
            backend.broker, backend.drain_error = broker, None
            with self.assertRaisesRegex(
                RunnerError, "workspace_command_output_too_large"
            ):
                backend.check_transport()
