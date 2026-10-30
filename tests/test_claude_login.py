import ast
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from laomedo.agents.agents.claude.auth.utils import mirror_login
from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.settings import CODES
from laomedo.agents.agents.claude.auth.resources.write_login import write_login

try:
    import py_docker
except ImportError:
    py_docker = None

IMAGE = "sha256:" + "a" * 64


class LoginMirrorTests(TestCase):
    def test_access_must_cover_the_execution_deadline(self):
        with (
            patch(
                "laomedo.agents.agents.claude.auth.utils.subprocess.run",
                side_effect=self.docker,
            ) as run,
            self.assertRaisesRegex(LocalClaudeLoginError, "claude_host_login_expired"),
        ):
            mirror_login(
                "laomedo-claude-profile",
                IMAGE,
                source=self.source,
                environment={},
                minimum_validity_seconds=7200,
            )
        self.assertFalse(any("run" in call.args[0] for call in run.call_args_list))

    def test_existing_refresh_capable_login_is_preserved(self):
        profile = Path(self.temp.name) / "profile"
        profile.mkdir()
        credentials = profile / ".credentials.json"
        original = b'{"claudeAiOauth":{"refreshToken":"internal-existing-login"}}'
        credentials.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "login_write_refused"):
            write_login(profile, 3, io.BytesIO(b"new"))
        self.assertEqual(credentials.read_bytes(), original)

    def test_runtime_opt_in_mirrors_before_auth_and_preserves_safe_error(self):
        from laomedo.agents.agents.claude.agent import ClaudeAgent
        from laomedo.agents.errors import RunnerError

        runner = object.__new__(ClaudeAgent)
        runner.turn_timeout = 180
        runner.container = SimpleNamespace(
            profile="laomedo-claude-unit",
            image_id=IMAGE,
            control=lambda *args, **kw: SimpleNamespace(
                exit_code=0,
                stdout=b'{"loggedIn":true,"authMethod":"claude.ai","orgId":"unit"}',
            ),
        )
        with (
            patch.dict("os.environ", {"LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN": "1"}),
            patch("laomedo.agents.agents.claude.agent.mirror_login") as mirror,
        ):
            self.assertTrue(runner._check_auth().startswith("sha256:"))
            mirror.assert_called_once_with(
                "laomedo-claude-unit", IMAGE, minimum_validity_seconds=180
            )
        for code in CODES:
            with (
                self.subTest(code=code),
                patch.dict("os.environ", {"LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN": "1"}),
                patch(
                    "laomedo.agents.agents.claude.agent.mirror_login",
                    side_effect=LocalClaudeLoginError(code),
                ),
                self.assertRaisesRegex(RunnerError, "^" + code + "$"),
            ):
                runner._check_auth()

    def setUp(self):
        if py_docker is None:
            self.skipTest("optional runner SDK is not installed")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = MagicMock()
        self.client.volumes.has_labels.return_value = True
        self.session = self.client.sessions.open.return_value.__enter__.return_value
        self.session.wait.return_value = 0
        self.session.read_frame.return_value = None
        factory = patch("py_docker.Client", return_value=self.client)
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        directory = patch(
            "laomedo.agents.agents.claude.auth.utils._private_directory",
            return_value=Path(self.temp.name),
        )
        directory.start()
        self.addCleanup(directory.stop)
        self.source = Path(self.temp.name) / "login.json"
        self.source.write_text(
            json.dumps(
                {
                    "claudeAiOauth": {
                        "accessToken": "internal-access",
                        "refreshToken": "internal-refresh",
                        "expiresAt": (time.time() + 3600) * 1000,
                        "scopes": ["user:inference"],
                    },
                    "unrelated": "private-profile",
                }
            )
        )

    def docker(self, command, **kwargs):
        if command[1:2] == ["--host"]:
            command = [command[0], *command[3:]]
        if command[1:3] == ["context", "inspect"]:
            value = [
                {
                    "Endpoints": {
                        "docker": {"Host": "npipe:////./pipe/dockerDesktopLinuxEngine"}
                    }
                }
            ]
        elif command[1:3] == ["volume", "inspect"]:
            value = [{"Labels": {"laomedo.provider": "claude"}}]
        else:
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(value).encode(), stderr=b""
        )

    def test_mirror_copies_only_access_and_retains_host_refresh_ownership(self):
        with patch(
            "laomedo.agents.agents.claude.auth.utils.subprocess.run",
            side_effect=self.docker,
        ) as run:
            mirror_login(
                "laomedo-claude-profile",
                IMAGE,
                source=self.source,
                environment={"PATH": "host", "ANTHROPIC_API_KEY": "excluded"},
            )
        written = self.session.write.call_args.args[0]
        payload = json.loads(written)
        self.assertEqual(payload["claudeAiOauth"]["accessToken"], "internal-access")
        self.assertEqual(payload["claudeAiOauth"]["refreshToken"], "")
        self.assertNotIn("internal-refresh", written.decode())
        self.assertNotIn("private-profile", written.decode())
        self.assertNotIn(
            "ANTHROPIC_API_KEY", self.factory.call_args.kwargs["environment"]
        )
        self.assertEqual(
            self.client.sessions.open.call_args.args[0].spec.network_mode, "none"
        )
        self.assertEqual(
            self.factory.call_args.args[0].endpoint,
            "npipe:////./pipe/dockerDesktopLinuxEngine",
        )
        self.assertNotIn("DOCKER_CONTEXT", self.factory.call_args.kwargs["environment"])
        self.assertNotIn("DOCKER_HOST", self.factory.call_args.kwargs["environment"])
        self.assertEqual(run.call_args.args[0], ["docker", "context", "inspect"])
        self.assertFalse(any("run" in call.args[0] for call in run.call_args_list))

    def test_local_context_is_pinned_despite_remote_host_override(self):
        with patch(
            "laomedo.agents.agents.claude.auth.utils.subprocess.run",
            side_effect=self.docker,
        ) as run:
            mirror_login(
                "laomedo-claude-profile",
                IMAGE,
                source=self.source,
                environment={
                    "DOCKER_CONTEXT": "desktop-linux",
                    "DOCKER_HOST": "tcp://remote:2375",
                },
            )
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["docker", "context", "inspect"])
        self.assertEqual(
            self.factory.call_args.args[0].endpoint,
            "npipe:////./pipe/dockerDesktopLinuxEngine",
        )
        self.assertNotIn("DOCKER_CONTEXT", self.factory.call_args.kwargs["environment"])
        self.assertNotIn("DOCKER_HOST", self.factory.call_args.kwargs["environment"])

    def test_remote_context_overrides_local_host_and_is_refused_before_read(self):
        source = SimpleNamespace(
            read_text=lambda **kw: self.fail("Credential must not be read")
        )
        result = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [{"Endpoints": {"docker": {"Host": "tcp://remote.example:2375"}}}]
            ).encode(),
        )
        with (
            patch(
                "laomedo.agents.agents.claude.auth.utils.subprocess.run",
                return_value=result,
            ),
            self.assertRaisesRegex(
                LocalClaudeLoginError, "claude_local_login_copy_failed"
            ),
        ):
            mirror_login(
                "laomedo-claude-profile",
                IMAGE,
                source=source,
                environment={
                    "DOCKER_HOST": "tcp://127.0.0.1:2375",
                    "DOCKER_CONTEXT": "remote",
                },
            )

    def test_remote_named_pipe_or_host_is_refused(self):
        for host in [
            "npipe:////server/pipe/docker_engine",
            "tcp://remote.example:2375",
            "unix://remote/socket",
            "tcp://127.0.0.1:2375",
        ]:
            with (
                self.subTest(host=host),
                self.assertRaisesRegex(
                    LocalClaudeLoginError, "claude_local_login_copy_failed"
                ),
            ):
                mirror_login(
                    "laomedo-claude-profile",
                    IMAGE,
                    source=self.source,
                    environment={"Docker_Host": host},
                )

    def test_missing_or_expired_access_never_writes_the_profile(self):
        for value, code in [
            ({}, "claude_host_login_unavailable"),
            (
                {"claudeAiOauth": {"accessToken": "internal", "expiresAt": 0}},
                "claude_host_login_expired",
            ),
        ]:
            self.source.write_text(json.dumps(value))
            with (
                patch(
                    "laomedo.agents.agents.claude.auth.utils.subprocess.run",
                    side_effect=self.docker,
                ) as run,
                self.assertRaisesRegex(LocalClaudeLoginError, code),
            ):
                mirror_login(
                    "laomedo-claude-profile", IMAGE, source=self.source, environment={}
                )
            self.assertFalse(
                any(call.args[0][1] == "run" for call in run.call_args_list)
            )

    def test_public_mirror_codes_have_catalogue_coverage(self):
        import laomedo.agents.agents.claude.auth.utils as claude_login

        trees = [
            ast.parse(path.read_text(encoding="utf-8-sig"))
            for path in (
                Path(claude_login.__file__),
                Path(claude_login.__file__).with_name("models.py"),
            )
        ]
        emitted = {
            n.value
            for tree in trees
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and n.value.startswith("claude_")
        }
        self.assertEqual(emitted, CODES)
        catalogue = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        self.assertEqual(CODES - catalogue.keys(), set())
