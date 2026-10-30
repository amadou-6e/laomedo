"""Internal failure controls; these do not establish live agent acceptance."""

from importlib.util import find_spec

import ast
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from laomedo.agents.agents.claude.container import CommandService
from laomedo.agents.agents.opencode.boundary import CommandBroker, IsolatedOpenCode
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.errors import RunnerError


class ProviderRecoveryTests(unittest.TestCase):
    """Keep previous-run recovery and fatal command results independent of model claims."""

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
            runner._opencode_catalog_lock = threading.Lock()
            runner._opencode_catalog_cached = None

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
            broker = CommandBroker(
                root, root, root, root, docker_endpoint="unix:///internal.sock"
            )
            self.addCleanup(broker.close)
            with patch("py_docker.Client") as client:
                client.return_value.__enter__.return_value.jobs.run.side_effect = (
                    OutputLimitError("internal limit")
                )
                self.assertEqual(broker.execute("pwd")["exit_code"], 125)
            backend = IsolatedOpenCode.__new__(IsolatedOpenCode)
            backend.broker, backend.drain_error = broker, None
            with self.assertRaisesRegex(
                RunnerError, "workspace_command_output_too_large"
            ):
                backend.check_transport()

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

    def test_retired_cli_paths_and_dynamic_codes_are_guarded(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "claude/container.py",
            "claude/agent.py",
            "opencode/boundary.py",
            "opencode/utils.py",
        ):
            tree = ast.parse(
                root.joinpath("src/laomedo/agents/agents", relative).read_text(
                    encoding="utf-8"
                )
            )
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                ):
                    self.assertNotIn(
                        (node.func.value.id, node.func.attr),
                        {("subprocess", "Popen"), ("subprocess", "run")},
                    )
        catalogue = json.loads(
            root.joinpath(
                "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text(encoding="utf-8")
        )
        for code in (
            "workspace_command_output_too_large",
            "opencode_workspace_command_failed",
            "opencode_command_service_closed",
            "opencode_controller_output_failed",
        ):
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip())
        component = ast.parse(
            root.joinpath(
                "src/laomedo/agents/interface/langflow/component.py"
            ).read_text(encoding="utf-8")
        )
        routed = next(
            ast.literal_eval(n.value)
            for n in component.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_ROUTABLE_ERRORS"
                for t in n.targets
            )
        )
        self.assertTrue(
            {
                "workspace_command_output_too_large",
                "opencode_workspace_command_failed",
                "opencode_command_service_closed",
                "opencode_controller_output_failed",
            }
            <= routed
        )
