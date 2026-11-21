"""Headless Codex teardown must drain retained native session ownership."""

import unittest
from unittest.mock import Mock, patch

from laomedo.agents.agents.codex.cli import main


class CodexCliTests(unittest.TestCase):
    def test_interrupted_listener_closes_agent_resources_and_listener(self):
        runner, server = Mock(), Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        arguments = [
            "codex-runner",
            "--state",
            "state",
            "--skill-store",
            "store",
            "--source-workspace",
            "source",
        ]
        with (
            patch("sys.argv", arguments),
            patch(
                "laomedo.agents.agents.codex.cli.AgentProviderRegistry.create_agent",
                return_value=runner,
            ),
            patch("laomedo.agents.agents.codex.cli.RunnerServer", return_value=server),
        ):
            with self.assertRaises(KeyboardInterrupt):
                main()
        runner.close.assert_called_once_with()
        server.server_close.assert_called_once_with()

    def test_cleanup_failure_still_closes_listener_and_remains_visible(self):
        runner, server = Mock(), Mock()
        runner.close.side_effect = RuntimeError("cleanup unconfirmed")
        arguments = [
            "codex-runner",
            "--state",
            "state",
            "--skill-store",
            "store",
            "--source-workspace",
            "source",
        ]
        with (
            patch("sys.argv", arguments),
            patch(
                "laomedo.agents.agents.codex.cli.AgentProviderRegistry.create_agent",
                return_value=runner,
            ),
            patch("laomedo.agents.agents.codex.cli.RunnerServer", return_value=server),
        ):
            with self.assertRaisesRegex(RuntimeError, "cleanup unconfirmed"):
                main()
        server.server_close.assert_called_once_with()
