"""Internal controls for generic Git isolation and the retired process paths."""

import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pydantic import SecretStr, ValidationError
from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandTimeout
from laomedo.git.models import (
    GitCommand,
    GitCredential,
    GitEnvironmentProfile,
    GitExecutionContext,
)
from laomedo.git.settings import MEDIATED_TOKEN_ENV


class SharedGitTests(unittest.TestCase):
    def test_profile_differences_and_private_credential_projection(self):
        runner = GitCommandRunner()
        home = Path("private-home")
        secret = "internal-control-token"
        credential = GitCredential(token=SecretStr(secret))
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_COUNT": "9",
                "GCM_TEST": "x",
                "GH_TOKEN": "ambient",
                "SSH_ASKPASS": "x",
                "HOMEDRIVE": "X:",
                "HOMEPATH": "ambient",
                MEDIATED_TOKEN_ENV: "unselected",
            },
        ):
            for profile in GitEnvironmentProfile:
                command = GitCommand(
                    arguments=["--version"],
                    context=GitExecutionContext(profile=profile),
                )
                env = runner.environment(command, home)
                for key in (
                    "GIT_CONFIG_COUNT",
                    "GCM_TEST",
                    "GH_TOKEN",
                    "SSH_ASKPASS",
                    "HOMEDRIVE",
                    "HOMEPATH",
                    MEDIATED_TOKEN_ENV,
                ):
                    self.assertNotIn(key, env)
                for key in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
                    self.assertEqual(env[key], str(home))
                self.assertEqual(
                    env.get("GIT_ASKPASS"),
                    "" if profile == GitEnvironmentProfile.HOST_TRANSPORT else None,
                )
                self.assertEqual(
                    env.get("GIT_OPTIONAL_LOCKS"),
                    "0" if profile == GitEnvironmentProfile.WORKSPACE else None,
                )
                self.assertEqual(
                    env.get("GIT_LFS_SKIP_SMUDGE"),
                    "1" if profile == GitEnvironmentProfile.WORKSPACE else None,
                )
            bound = command.model_copy(update={"credential": credential})
            self.assertEqual(
                runner.environment(bound, home)[MEDIATED_TOKEN_ENV], secret
            )
            self.assertNotIn(secret, " ".join(runner._arguments(bound, home)))
            for value in (
                repr(bound),
                bound.model_dump_json(),
                repr(credential),
                credential.model_dump_json(),
            ):
                self.assertNotIn(secret, value)

    def test_invalid_credential_does_not_echo_input(self):
        with self.assertRaises(ValidationError) as found:
            GitCredential(token=SecretStr("private-value\ninvalid"))
        self.assertNotIn("private-value", str(found.exception))

    def test_startup_failure_clears_selected_token_without_mutating_host(self):
        environments = []

        def denied(_arguments, **options):
            environments.append(options["env"])
            raise FileNotFoundError("git unavailable")

        command = GitCommand(
            arguments=["--version"],
            context=GitExecutionContext(),
            credential=GitCredential(token=SecretStr("private-token")),
        )
        with patch.dict(os.environ, {MEDIATED_TOKEN_ENV: "host-value"}):
            with patch("laomedo.git.command.subprocess.Popen", side_effect=denied):
                with self.assertRaises(FileNotFoundError):
                    GitCommandRunner().run(command)
            self.assertEqual(os.environ[MEDIATED_TOKEN_ENV], "host-value")
        self.assertEqual(len(environments), 1)
        self.assertNotIn(MEDIATED_TOKEN_ENV, environments[0])

    def test_profiles_preserve_stdin_and_both_process_group_options(self):
        home = Path(tempfile.gettempdir())
        for platform in ("nt", "posix"):
            for profile in GitEnvironmentProfile:
                process = MagicMock(returncode=0)
                process.communicate.return_value = (b"git version", b"")
                command = GitCommand(
                    arguments=["--version"],
                    context=GitExecutionContext(profile=profile, home=home),
                )
                with (
                    patch("laomedo.git.command.os.name", platform),
                    patch(
                        "laomedo.git.command.subprocess.CREATE_NEW_PROCESS_GROUP",
                        0x200,
                        create=True,
                    ),
                    patch(
                        "laomedo.git.command.subprocess.Popen", return_value=process
                    ) as spawn,
                ):
                    GitCommandRunner().run(command)
                options = spawn.call_args.kwargs
                if profile == GitEnvironmentProfile.WORKSPACE:
                    self.assertEqual(options["stdin"], subprocess.DEVNULL)
                else:
                    self.assertNotIn("stdin", options)
                self.assertEqual("creationflags" in options, platform == "nt")
                if platform == "nt":
                    self.assertEqual(options["creationflags"], 0x200)
                self.assertEqual("start_new_session" in options, platform == "posix")

    def test_timeout_closes_inherited_pipes_and_retains_uncertainty(self):
        process = MagicMock(pid=123, returncode=None)
        process.poll.return_value = None
        process.communicate.side_effect = subprocess.TimeoutExpired(["git"], 0.1)
        process.wait.side_effect = subprocess.TimeoutExpired(["git"], 5)
        home = Path(tempfile.gettempdir())
        command = GitCommand(
            arguments=["--version"], context=GitExecutionContext(home=home, timeout=0.1)
        )
        with (
            patch("laomedo.git.command.subprocess.Popen", return_value=process),
            patch.object(
                GitCommandRunner, "_stop_tree", wraps=GitCommandRunner()._stop_tree
            ),
            patch(
                "laomedo.git.command.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0),
            ),
            patch("laomedo.git.command.os.killpg", create=True),
        ):
            with self.assertRaises(GitCommandTimeout) as found:
                GitCommandRunner().run(command)
        self.assertFalse(found.exception.cleanup_verified)
        process.kill.assert_called_once()
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_generic_git_has_no_feature_dependencies_and_old_runners_are_removed(self):
        source = Path(__file__).resolve().parents[1] / "src/laomedo"
        for path in (source / "git").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "laomedo."
                ):
                    self.assertTrue(
                        node.module.startswith("laomedo.git"), (path, node.module)
                    )
        self.assertFalse((source / "agents/workspaces/git.py").exists())
        retired = {
            "_run_bounded_tree",
            "_bounded_git",
            "_base_git_environment",
            "_git_environment",
            "_credential_environment",
        }
        for relative in (
            "agents/workspaces",
            "github/transport/git",
            "host/publication/verified",
            "skills/workspace",
            "host/mediation",
        ):
            for path in (source / relative).rglob("*.py"):
                tree = ast.parse(path.read_text())
                self.assertFalse(
                    {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
                    & retired,
                    path,
                )


if __name__ == "__main__":
    unittest.main()
