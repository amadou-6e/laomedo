"""Check the actual public run contract without launching native providers."""

from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from uuid import uuid4
import inspect
import unittest
from unittest.mock import patch

from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.claude.agent import ClaudeAgent
from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.errors import RunnerError


class InteractionContractTests(unittest.TestCase):
    def test_every_provider_accepts_the_declared_interaction_arguments(self):
        for kind in (ClaudeAgent, CodexAgent, OpenCodeAgent):
            for name in (
                "start",
                "start_async",
                "resume",
                "status",
                "cancel",
                "lookup_request",
            ):
                with self.subTest(provider=kind.provider, operation=name):
                    declared = inspect.signature(getattr(BaseAgent, name))
                    implementation = inspect.signature(getattr(kind, name))
                    self.assertEqual(
                        list(declared.parameters), list(implementation.parameters)
                    )
                    for parameter in declared.parameters:
                        self.assertEqual(
                            declared.parameters[parameter].kind,
                            implementation.parameters[parameter].kind,
                        )
                        self.assertEqual(
                            declared.parameters[parameter].default,
                            implementation.parameters[parameter].default,
                        )
                    self.assertFalse(inspect.iscoroutinefunction(getattr(kind, name)))

    def test_unsupported_timeout_refuses_resume_before_record_access(self):
        for kind in (CodexAgent, OpenCodeAgent):
            with self.subTest(provider=kind.provider):
                agent = object.__new__(kind)
                with (
                    patch.object(agent, "status") as status,
                    patch.object(agent, "_execute") as execute,
                ):
                    with self.assertRaisesRegex(
                        RunnerError, "run_timeout_not_supported"
                    ):
                        agent.resume(
                            "not-admitted",
                            "continue",
                            expected_post_run_hash="hash",
                            expected_thread_id="thread",
                            model="model",
                            effort="default",
                            run_timeout_seconds=30,
                        )
                    status.assert_not_called()
                    execute.assert_not_called()

    def test_unsupported_timeout_refuses_fresh_and_http_resume_before_dispatch(self):
        for kind in (CodexAgent, OpenCodeAgent):
            with self.subTest(provider=kind.provider):
                agent = object.__new__(kind)
                with (
                    patch.object(agent, "_execute") as execute,
                    patch.object(agent, "_mirror_host_login") as login,
                ):
                    with self.assertRaisesRegex(
                        RunnerError, "run_timeout_not_supported"
                    ):
                        BaseAgent._prepare(agent, {"run_timeout_seconds": 30})
                    with self.assertRaisesRegex(
                        RunnerError, "run_timeout_not_supported"
                    ):
                        agent.prepare_resume(
                            "not-admitted", {"run_timeout_seconds": 30}
                        )
                    execute.assert_not_called()
                    login.assert_not_called()

    def test_public_start_operations_refuse_timeout_without_admission(self):
        for kind in (CodexAgent, OpenCodeAgent):
            with (
                self.subTest(provider=kind.provider),
                TemporaryDirectory() as temporary,
            ):
                agent = object.__new__(kind)
                agent.state = Path(temporary)
                (agent.state / "runs").mkdir()
                agent.request_lock = threading.Lock()
                request = {
                    "request_id": str(uuid4()),
                    "task": "task",
                    "model": "provider/model",
                    "effort": "default",
                    "run_timeout_seconds": 30,
                }
                with patch.object(agent, "_execute") as execute:
                    for operation in (agent.start, agent.start_async):
                        with self.assertRaisesRegex(
                            RunnerError, "run_timeout_not_supported"
                        ):
                            operation(request)
                    execute.assert_not_called()
                self.assertEqual(list((agent.state / "runs").iterdir()), [])

    def test_no_timeout_override_preserves_native_binding_refusals(self):
        for kind in (CodexAgent, OpenCodeAgent):
            with self.subTest(provider=kind.provider):
                agent = object.__new__(kind)
                with patch.object(
                    agent, "status", side_effect=RunnerError("invalid_run_id")
                ) as status:
                    with self.assertRaisesRegex(RunnerError, "invalid_run_id"):
                        agent.resume(
                            "invalid",
                            "continue",
                            expected_post_run_hash="hash",
                            expected_thread_id="thread",
                            model="provider/model",
                            effort="default",
                            run_timeout_seconds=None,
                        )
                    status.assert_called_once_with("invalid")

    def test_claude_keeps_native_timeout_validation(self):
        agent = object.__new__(ClaudeAgent)
        with patch.object(agent, "status") as status:
            for timeout in (0, True, 86401):
                with self.subTest(timeout=timeout):
                    with self.assertRaisesRegex(
                        RunnerError, "claude_turn_timeout_invalid"
                    ):
                        agent.resume(
                            "invalid",
                            "continue",
                            expected_post_run_hash="hash",
                            expected_thread_id="thread",
                            model="sonnet",
                            effort="low",
                            run_timeout_seconds=timeout,
                        )
            status.assert_not_called()
