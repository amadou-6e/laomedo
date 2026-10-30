import ast
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from laomedo.agents.agents.claude.auth.utils import mirror_login
from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.settings import CODES

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
        import subprocess
        import sys

        with patch(
            "laomedo.agents.agents.claude.auth.utils.subprocess.run",
            side_effect=self.docker,
        ) as run:
            mirror_login(
                "laomedo-claude-profile", IMAGE, source=self.source, environment={}
            )
        call = run.call_args
        script = call.args[0][-1]
        profile = Path(self.temp.name) / "profile"
        profile.mkdir()
        credentials = profile / ".credentials.json"
        original = b'{"claudeAiOauth":{"refreshToken":"internal-existing-login"}}'
        credentials.write_bytes(original)
        script = script.replace("p='/profile/config'", "p=" + repr(str(profile)))
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=call.kwargs["input"],
            capture_output=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
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
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
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
        call = run.call_args
        payload = json.loads(call.kwargs["input"])
        self.assertEqual(payload["claudeAiOauth"]["accessToken"], "internal-access")
        self.assertEqual(payload["claudeAiOauth"]["refreshToken"], "")
        self.assertNotIn("internal-refresh", call.kwargs["input"].decode())
        self.assertNotIn("private-profile", call.kwargs["input"].decode())
        self.assertNotIn("ANTHROPIC_API_KEY", call.kwargs["env"])
        self.assertIn("--network=none", call.args[0])
        self.assertEqual(
            call.args[0][1:3], ["--host", "npipe:////./pipe/dockerDesktopLinuxEngine"]
        )
        self.assertNotIn("DOCKER_CONTEXT", call.kwargs["env"])
        self.assertNotIn("DOCKER_HOST", call.kwargs["env"])
        self.assertEqual(call.kwargs["timeout"], 20)

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
        for call in run.call_args_list[1:]:
            self.assertEqual(
                call.args[0][1:3],
                ["--host", "npipe:////./pipe/dockerDesktopLinuxEngine"],
            )
            self.assertNotIn("DOCKER_CONTEXT", call.kwargs["env"])
            self.assertNotIn("DOCKER_HOST", call.kwargs["env"])

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

        tree = ast.parse(Path(claude_login.__file__).read_text(encoding="utf-8-sig"))
        emitted = {
            n.value
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
