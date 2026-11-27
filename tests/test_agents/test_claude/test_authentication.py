"""Native authentication and Docker control deadline invariants."""

from importlib.util import find_spec
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

try:
    import py_docker
except ImportError:
    py_docker = None


@unittest.skipIf(
    py_docker is None or find_spec("acp") is None,
    "optional runner extras are not installed",
)
class NativeAuthDeadlineTests(unittest.TestCase):
    def test_remaining_deadline_bounds_native_auth(self):
        from laomedo.agents.agents.claude.agent import ClaudeAgent

        agent = object.__new__(ClaudeAgent)
        agent._prepare_credentials = MagicMock()
        agent.container = MagicMock()
        agent.container.control.return_value = SimpleNamespace(
            exit_code=0, stdout=b'{"loggedIn":true,"authMethod":"claude.ai"}'
        )
        with patch(
            "laomedo.agents.agents.claude.agent.time.monotonic", return_value=80
        ):
            agent._check_auth(timeout=60, minimum_validity_seconds=100, deadline=100)
        agent._prepare_credentials.assert_called_once_with(
            minimum_validity_seconds=100, deadline=100
        )
        agent.container.control.assert_called_once_with(
            ["auth", "status"], timeout=20, deadline=100
        )

    def test_expired_attempt_never_dispatches_native_auth(self):
        from laomedo.agents.agents.claude.agent import ClaudeAgent
        from laomedo.agents.errors import RunnerError

        agent = object.__new__(ClaudeAgent)
        agent._prepare_credentials, agent.container = MagicMock(), MagicMock()
        with (
            patch(
                "laomedo.agents.agents.claude.agent.time.monotonic", return_value=100
            ),
            self.assertRaisesRegex(RunnerError, "claude_turn_timeout"),
        ):
            agent._check_auth(deadline=100)
        agent.container.control.assert_not_called()


@unittest.skipIf(py_docker is None, "optional runner SDK is not installed")
class ContainerControlDeadlineTests(unittest.TestCase):
    def test_client_keeps_selected_endpoint_without_ambient_configuration(self):
        from laomedo.agents.agents.claude.policy import ClaudeRuntimePolicy

        runtime = object.__new__(ClaudeRuntimePolicy)
        runtime.docker_endpoint = "npipe:////./pipe/selected-control"
        with patch("py_docker.Client") as factory:
            with runtime.client():
                pass
            factory.assert_called_once_with(
                environment={"DOCKER_HOST": runtime.docker_endpoint}
            )
        with (
            patch("py_docker.Client") as factory,
            patch(
                "laomedo.agents.agents.claude.policy.time.monotonic", return_value=80
            ),
        ):
            with runtime.client(deadline=100):
                pass
        self.assertEqual(factory.call_args.kwargs["environment"], {})
        self.assertEqual(
            factory.call_args.kwargs["settings"].endpoint, runtime.docker_endpoint
        )
        self.assertEqual(factory.call_args.kwargs["settings"].timeout_seconds, 20)

    def test_expired_control_budget_never_connects_to_docker(self):
        from laomedo.agents.agents.claude.policy import ClaudeRuntimePolicy
        from laomedo.agents.errors import RunnerError

        runtime = object.__new__(ClaudeRuntimePolicy)
        runtime.docker_endpoint = "npipe:////./pipe/selected-control"
        with (
            patch("py_docker.Client") as factory,
            patch(
                "laomedo.agents.agents.claude.policy.time.monotonic",
                return_value=100,
            ),
            self.assertRaisesRegex(RunnerError, "claude_turn_timeout"),
        ):
            with runtime.client(deadline=100):
                self.fail("Expired control reached its body")
        factory.assert_not_called()
