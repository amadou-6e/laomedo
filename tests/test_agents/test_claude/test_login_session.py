"""Internal copy protocol and deadline controls, never native login acceptance."""

import io
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.resources.write_login import write_login
from laomedo.agents.agents.claude.auth.utils import _local_endpoint, mirror_login

try:
    import py_docker
except ImportError:
    py_docker = None


class AccessLoginWriterTests(unittest.TestCase):
    def test_exact_length_does_not_require_eof_and_replaces_with_private_file(self):
        payload = (
            b'{"claudeAiOauth":{"accessToken":"internal-control","refreshToken":""}}'
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root / ".login-stale"
            stale.write_bytes(b"old-control")
            source = io.BytesIO(payload + b"must-remain-unread")
            write_login(root, len(payload), source)
            self.assertEqual(source.tell(), len(payload))
            self.assertEqual(root.joinpath(".credentials.json").read_bytes(), payload)
            self.assertFalse(stale.exists())
            self.assertEqual(list(root.glob(".login-*")), [])

    def test_incomplete_input_preserves_existing_file_and_stale_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ".credentials.json"
            target.write_text('{"claudeAiOauth":{"refreshToken":""}}', encoding="utf-8")
            before = target.read_bytes()
            stale = root / ".login-stale"
            stale.write_bytes(b"old-control")
            with self.assertRaisesRegex(ValueError, "login_input_incomplete"):
                write_login(root, 8, io.BytesIO(b"short"))
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(stale.exists())

    def test_refresh_capable_login_is_preserved_without_reading_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ".credentials.json"
            target.write_text(
                '{"claudeAiOauth":{"refreshToken":"internal-control"}}',
                encoding="utf-8",
            )
            before = target.read_bytes()
            source = io.BytesIO(b"new")
            with self.assertRaisesRegex(ValueError, "login_write_refused"):
                write_login(root, 3, source)
            self.assertEqual(source.tell(), 0)
            self.assertEqual(target.read_bytes(), before)


class LocalEndpointTests(unittest.TestCase):
    def test_explicit_local_pipe_only_accepts_proven_cli_spelling(self):
        admitted = "npipe:////./pipe/dockerDesktopLinuxEngine"
        with patch("laomedo.agents.agents.claude.auth.utils.subprocess.run") as run:
            self.assertEqual(
                _local_endpoint({"DOCKER_HOST": admitted}, 100000000000.0), admitted
            )
            for refused in (
                "tcp://remote:2375",
                "npipe://./pipe/docker_engine",
                "NPIPE:////./pipe/docker_engine",
                "npipe:////./pipe/has/slash",
            ):
                with (
                    self.subTest(refused=refused),
                    self.assertRaises(LocalClaudeLoginError),
                ):
                    _local_endpoint({"DOCKER_HOST": refused}, 100000000000.0)
            run.assert_not_called()

    def test_context_selection_keeps_original_bare_cli_argv_and_environment(self):
        endpoint = "npipe:////./pipe/docker_engine"
        environment = {
            "DOCKER_CONTEXT": "selected",
            "DOCKER_HOST": "tcp://sentinel:2375",
        }
        with patch(
            "laomedo.agents.agents.claude.auth.utils.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [{"Endpoints": {"docker": {"Host": endpoint}}}]
                ).encode(),
            ),
        ) as run:
            self.assertEqual(_local_endpoint(environment, 100000000000.0), endpoint)
        self.assertEqual(run.call_args.args[0], ["docker", "context", "inspect"])
        self.assertEqual(run.call_args.kwargs["env"], environment)
        self.assertEqual(run.call_args.kwargs["timeout"], 20.0)


@unittest.skipIf(py_docker is None, "optional runner SDK is not installed")
class AccessLoginSessionTests(unittest.TestCase):
    def test_only_access_bytes_use_owned_stdin_after_admission(self):
        events = []
        source = MagicMock()
        value = {
            "accessToken": "internal-access-control",
            "expiresAt": 9999999999999,
            "refreshToken": "must-never-copy-control",
        }
        source.read_text.side_effect = lambda **_: events.append(
            "source"
        ) or json.dumps({"claudeAiOauth": value})
        client = MagicMock()
        client.volumes.has_labels.side_effect = (
            lambda *_: events.append("volume") or True
        )
        session = client.sessions.open.return_value.__enter__.return_value
        session.read_frame.return_value = None
        session.wait.return_value = 0
        environment = {
            "DOCKER_HOST": "npipe:////./pipe/docker_engine",
            "UNRELATED_SECRET": "must-not-propagate-control",
        }
        with (
            patch("py_docker.Client", return_value=client) as factory,
            patch(
                "laomedo.agents.agents.claude.auth.utils._private_directory",
                return_value=Path(tempfile.gettempdir()),
            ) as directory,
            patch.dict(
                "os.environ",
                {"LAOMEDO_CLAUDE_LOGIN_STATE_DIR": "ambient-must-not-leak-control"},
            ),
        ):
            mirror_login(
                "laomedo-claude-control",
                "sha256:" + "1" * 64,
                source=source,
                environment=environment,
            )
        self.assertEqual(events, ["volume", "source"])
        self.assertIsNone(directory.call_args.args[1].private_state_directory)
        self.assertNotIn("UNRELATED_SECRET", factory.call_args.kwargs["environment"])
        self.assertNotIn("DOCKER_HOST", factory.call_args.kwargs["environment"])
        request = client.sessions.open.call_args.args[0]
        written = session.write.call_args.args[0]
        self.assertEqual(json.loads(written)["claudeAiOauth"]["refreshToken"], "")
        self.assertNotIn(b"must-never-copy", written)
        self.assertEqual(request.spec.command[-1], str(len(written)))
        self.assertNotIn("internal-access-control", repr(request.spec.command))
        self.assertEqual(request.spec.network_mode, "none")
        self.assertTrue(request.spec.read_only)
        self.assertTrue(request.spec.stdin_open)
        self.assertEqual(request.spec.log_driver, "none")
        self.assertEqual(request.receipt_path.name, "laomedo-claude-control.json")
        self.assertGreater(client.sessions.open.call_args.kwargs["cleanup_seconds"], 0)
        client.sessions.open.return_value.__exit__.assert_called_once()
        client.close.assert_called_once()

    def test_volume_refusal_never_reads_source_or_opens_session(self):
        source, client = MagicMock(), MagicMock()
        client.volumes.has_labels.return_value = False
        with (
            patch("py_docker.Client", return_value=client),
            patch(
                "laomedo.agents.agents.claude.auth.utils._private_directory",
                return_value=Path(tempfile.gettempdir()),
            ),
            self.assertRaisesRegex(
                LocalClaudeLoginError, "claude_local_login_copy_failed"
            ),
        ):
            mirror_login(
                "laomedo-claude-control",
                "sha256:" + "1" * 64,
                source=source,
                environment={"DOCKER_HOST": "npipe:////./pipe/docker_engine"},
            )
        source.read_text.assert_not_called()
        client.sessions.open.assert_not_called()
        client.close.assert_called_once()


@unittest.skipIf(
    py_docker is None or find_spec("acp") is None,
    "optional runner extras are not installed",
)
class NativeAuthDeadlineTests(unittest.TestCase):
    def test_copy_time_is_subtracted_before_native_auth(self):
        from laomedo.agents.agents.claude.agent import ClaudeAgent

        agent = object.__new__(ClaudeAgent)
        agent._mirror_host_login = MagicMock()
        agent.container = MagicMock()
        agent.container.control.return_value = SimpleNamespace(
            exit_code=0, stdout=b'{"loggedIn":true,"authMethod":"claude.ai"}'
        )
        with patch(
            "laomedo.agents.agents.claude.agent.time.monotonic", return_value=80
        ):
            agent._check_auth(timeout=60, minimum_validity_seconds=100, deadline=100)
        agent._mirror_host_login.assert_called_once_with(
            minimum_validity_seconds=100, deadline=100
        )
        agent.container.control.assert_called_once_with(
            ["auth", "status"], timeout=20, deadline=100
        )

    def test_expired_attempt_never_dispatches_native_auth(self):
        from laomedo.agents.agents.claude.agent import ClaudeAgent
        from laomedo.agents.errors import RunnerError

        agent = object.__new__(ClaudeAgent)
        agent._mirror_host_login, agent.container = MagicMock(), MagicMock()
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
        from laomedo.agents.agents.claude.container import ClaudeContainer

        runtime = object.__new__(ClaudeContainer)
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
                "laomedo.agents.agents.claude.container.time.monotonic", return_value=80
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
        from laomedo.agents.agents.claude.container import ClaudeContainer
        from laomedo.agents.errors import RunnerError

        runtime = object.__new__(ClaudeContainer)
        runtime.docker_endpoint = "npipe:////./pipe/selected-control"
        with (
            patch("py_docker.Client") as factory,
            patch(
                "laomedo.agents.agents.claude.container.time.monotonic",
                return_value=100,
            ),
            self.assertRaisesRegex(RunnerError, "claude_turn_timeout"),
        ):
            with runtime.client(deadline=100):
                self.fail("Expired control reached its body")
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
