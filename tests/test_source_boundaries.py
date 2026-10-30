"""D2 internal source contract controls; these do not establish live acceptance."""

import ast
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from pydantic import SecretStr, ValidationError

from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandCleanupError, GitCommandLimitExceeded
from laomedo.git.models import (
    GitCommand,
    GitCredential,
    GitEnvironmentProfile,
    GitExecutionBudget,
    GitExecutionContext,
)
from laomedo.skills.interface.sources.client import source_request
from laomedo.skills.inspection.settings import MAX_FILE_BYTES
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.repository import GitSkillSource
from laomedo.skills.sources.staging import SkillSourceStagingDirectory

ROOT = Path(__file__).resolve().parents[1]


class SourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def command(self, **changes):
        values = dict(
            arguments=["--version"],
            cwd=self.root,
            context=GitExecutionContext(
                profile=GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY,
                hooks_path=Path(self.root, "no-hooks"),
            ),
            budget=GitExecutionBudget(stdout_limit=128),
        )
        values.update(changes)
        return GitCommand(**values)

    def test_read_profile_preserves_exact_narrow_environment_and_ordered_argv(self):
        runner = GitCommandRunner()
        command = self.command()
        ambient = {
            "PATH": "native-bin",
            "TEMP": "temporary",
            "SystemRoot": "system",
            "HOME": "private-home",
            "HTTP_PROXY": "private-proxy",
            "GIT_CONFIG_PARAMETERS": "private-config",
            "GH_TOKEN": "private-token",
            "OPENAI_API_KEY": "private-provider",
        }
        expected_root = "SYSTEMROOT" if os.name == "nt" else "SystemRoot"
        with patch.dict(os.environ, ambient, clear=True):
            self.assertEqual(
                runner.environment(command, self.root),
                {
                    "PATH": "native-bin",
                    "TEMP": "temporary",
                    expected_root: "system",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_ASKPASS": "",
                    "SSH_ASKPASS": "",
                },
            )
        expected = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.hooksPath=" + str(Path(self.root, "no-hooks")),
            "-c",
            "http.followRedirects=false",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            "--version",
        ]
        self.assertEqual(runner._arguments(command, self.root), expected)
        file_command = self.command(
            context=command.context.model_copy(
                update={"profile": GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY}
            )
        )
        self.assertEqual(
            runner._arguments(file_command, self.root),
            ["git", "-c", "protocol.file.allow=always", *expected[1:]],
        )

    def test_read_profile_rejects_overrides_and_revalidates_mutable_values(self):
        context = self.command().context
        for changes in (
            {"configuration": [("protocol.file.allow", "always")]},
            {"directory": self.root},
            {"cwd": None},
            {"budget": None},
            {"credential": GitCredential(token=SecretStr("internal-token"))},
            {"context": context.model_copy(update={"extra_env": {"HOME": "private"}})},
            {"context": context.model_copy(update={"home": self.root})},
            {"arguments": ["push", "origin", "HEAD"]},
            {"arguments": ["fetch", "--upload-pack=unsafe", "origin"]},
            {"arguments": ["-c", "protocol.file.allow=always", "clone"]},
        ):
            with (
                self.subTest(changes=list(changes)),
                self.assertRaises(ValidationError),
            ):
                self.command(**changes)
        command = self.command()
        command.arguments[:] = ["push", "origin", "HEAD"]
        with (
            patch("laomedo.git.command.subprocess.Popen") as launch,
            self.assertRaisesRegex(ValueError, "git_read_profile_invalid"),
        ):
            GitCommandRunner().run(command)
        launch.assert_not_called()

    def test_budget_and_private_paths_are_not_serialized(self):
        command = self.command(
            budget=GitExecutionBudget(stdout_limit=0, check_budget=lambda: None)
        )
        payload = command.model_dump_json()
        self.assertNotIn(str(self.root), payload)
        self.assertNotIn("check_budget", payload)
        self.assertNotIn("operation_deadline", payload)
        self.assertNotIn("private-token", repr(command))
        for values in (
            {"stdout_limit": 1, "operation_deadline": float("nan")},
            {"stdout_limit": 1, "poll_seconds": float("inf")},
        ):
            with self.assertRaises(ValidationError):
                GitExecutionBudget(**values)

    def test_confirmed_and_uncertain_cleanup_categories_remain_distinct(self):
        for error, expected in (
            (GitCommandLimitExceeded(), "repository_limit_exceeded"),
            (GitCommandCleanupError(), "repository_cleanup_unverified"),
        ):
            runner = MagicMock()
            runner.run.side_effect = error
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(SourceError, expected),
            ):
                GitSkillSource(self.root, runner=runner)._run(self.root, ["--version"])

    def test_each_repository_command_retains_its_existing_cap_and_operation_deadline(
        self,
    ):
        runner = MagicMock()
        source = GitSkillSource(self.root, runner=runner)
        url = "https://github.com/example/skills.git"
        folder = Path(self.root, hashlib.sha256(url.encode()).hexdigest())
        folder.mkdir()
        deadline = time.monotonic() + 60
        runner.run.side_effect = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"refs/heads/main\n", b""),
            subprocess.CompletedProcess([], 0, b"a" * 40 + b"\n", b""),
        ]
        state = source.repository(url, refresh=True, deadline=deadline)
        commands = [call.args[0] for call in runner.run.call_args_list]
        self.assertEqual(
            [command.arguments[0] for command in commands],
            ["fetch", "for-each-ref", "rev-parse"],
        )
        self.assertEqual(
            [command.budget.stdout_limit for command in commands],
            [4 * 1024 * 1024, 64 * 1024, 1024],
        )
        runner.reset_mock()
        runner.run.side_effect = None
        runner.run.return_value = subprocess.CompletedProcess(
            [], 0, b"100644 blob " + b"a" * 40 + b"\tSKILL.md\0", b""
        )
        entries = source.entries(folder, state.refs[0].commit, deadline)
        self.assertEqual(
            runner.run.call_args.args[0].budget.stdout_limit, 2 * 1024 * 1024
        )
        commands.append(runner.run.call_args.args[0])
        runner.reset_mock()
        runner.run.side_effect = [
            subprocess.CompletedProcess([], 0, b"10", b""),
            subprocess.CompletedProcess([], 0, b"skillbytes\n", b""),
        ]
        self.assertEqual(
            source.read_blob(folder, entries["SKILL.md"], deadline), b"skillbytes\n"
        )
        reads = [call.args[0] for call in runner.run.call_args_list]
        self.assertEqual(
            [command.budget.stdout_limit for command in reads], [128, MAX_FILE_BYTES]
        )
        commands.extend(reads)
        self.assertTrue(
            all(command.budget.operation_deadline == deadline for command in commands)
        )

    def test_active_native_process_limits_and_exit_between_polls_preserve_categories(
        self,
    ):
        original = subprocess.Popen
        for mode, limit, expected in (
            (["emit", "128", "0"], 128, None),
            (["emit", "129", "0"], 128, "repository_access_unavailable"),
            (["emit", "256", "60"], 128, "repository_limit_exceeded"),
            (["wait", "60"], 128, "repository_limit_exceeded"),
        ):
            processes = []

            def launch(arguments, **options):
                if arguments[0] != "git":
                    return original(arguments, **options)
                process = original(
                    [sys.executable, str(ROOT / "tests/git_process_control.py"), *mode],
                    **options,
                )
                processes.append(process)
                if mode[0] == "emit" and mode[-1] == "0":
                    process.wait(timeout=20)
                return process

            with self.subTest(mode=mode), patch("subprocess.Popen", new=launch):
                try:
                    deadline = time.monotonic() + (0.8 if mode[0] == "wait" else 30)
                    source = GitSkillSource(self.root)
                    if expected:
                        with self.assertRaises(SourceError) as raised:
                            source._run(
                                self.root, ["--version"], limit, deadline=deadline
                            )
                        # Native cleanup may exhaust its deadline under load. That
                        # is an explicit uncertainty outcome, never confirmed cleanup.
                        self.assertIn(
                            raised.exception.code,
                            {expected, "repository_cleanup_unverified"},
                        )
                    else:
                        self.assertEqual(
                            len(
                                source._run(
                                    self.root, ["--version"], limit, deadline=deadline
                                )
                            ),
                            limit,
                        )
                finally:
                    for process in processes:
                        if process.poll() is None:
                            GitCommandRunner()._stop_tree(
                                process, deadline=time.monotonic() + 5
                            )
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(
                    processes[0].poll(), "The test-owned process remains active"
                )

    def test_startup_failure_and_shared_operation_budget_are_not_reset(self):
        source = GitSkillSource(self.root)
        runner = source.runner
        with (
            patch(
                "laomedo.git.command.subprocess.Popen",
                side_effect=FileNotFoundError("internal startup control"),
            ),
            self.assertRaises(FileNotFoundError),
        ):
            source._run(self.root, ["--version"])
        deadline = time.monotonic() - 1
        command = self.command(
            budget=GitExecutionBudget(stdout_limit=128, operation_deadline=deadline)
        )
        self.assertEqual(command.budget.operation_deadline, deadline)
        seen = []

        def record(command):
            seen.append(command.budget.operation_deadline)
            return subprocess.CompletedProcess(["git"], 0, b"", b"")

        with patch.object(runner, "run", side_effect=record):
            source._run(self.root, ["--version"], deadline=deadline)
            source._run(self.root, ["--version"], deadline=deadline)
        self.assertEqual(seen, [deadline, deadline])

    def test_budgeted_cleanup_uses_one_deadline_without_changing_legacy_waits(self):
        runner = GitCommandRunner()
        with patch(
            "laomedo.git.command.time.monotonic", side_effect=[10.0, 12.0, 16.0]
        ):
            self.assertEqual(runner._cleanup_timeout(15.0), 5.0)
            self.assertEqual(runner._cleanup_timeout(15.0), 3.0)
            self.assertEqual(runner._cleanup_timeout(15.0), 0.0)
        with patch("laomedo.git.command.time.monotonic") as clock:
            self.assertEqual(runner._cleanup_timeout(None), 5)
            clock.assert_not_called()

    def test_unconfirmed_native_cleanup_never_reports_a_confirmed_limit(self):
        runner = GitCommandRunner()
        process = MagicMock()
        process.poll.return_value = None
        command = self.command(
            budget=GitExecutionBudget(stdout_limit=0, operation_deadline=-1.0)
        )
        with (
            patch.object(runner, "_start_process", return_value=process),
            patch.object(runner, "_stop_tree", return_value=False),
            self.assertRaises(GitCommandCleanupError) as raised,
        ):
            runner.run(command)
        self.assertFalse(raised.exception.cleanup_verified)
        with (
            patch.object(runner, "_start_process", return_value=process),
            patch.object(runner, "_stop_tree", side_effect=PermissionError("PRIVATE")),
            self.assertRaises(GitCommandCleanupError),
        ):
            runner.run(command)

    def test_uncertain_clone_staging_is_retained_but_ordinary_failure_is_removed(self):
        for code in ("repository_cleanup_unverified", "repository_limit_exceeded"):
            source = GitSkillSource(self.root)
            with (
                patch.object(source, "_run", side_effect=SourceError(code)),
                self.assertRaisesRegex(SourceError, code),
            ):
                source.repository(
                    "https://github.com/example/skills.git",
                    deadline=time.monotonic() + 1,
                )
            directories = list(self.root.glob("clone-*"))
            self.assertEqual(bool(directories), code == "repository_cleanup_unverified")
            for directory in directories:
                # Only this test's stopped/mock clone owns these files.
                directory.rmdir()
        ordinary = SkillSourceStagingDirectory(dir=self.root)
        with ordinary as directory:
            Path(directory, "file").write_bytes(b"bytes")
        self.assertFalse(Path(directory).exists())
        retained = SkillSourceStagingDirectory(dir=self.root)
        with retained as directory:
            retained.preserve()
        retained.cleanup()
        self.assertTrue(Path(directory).exists())
        Path(directory).rmdir()

    def test_client_only_forwards_bounded_exact_cleanup_category_and_closes_errors(
        self,
    ):
        token = Path(self.root, "token")
        token.write_text("internal-test-token-" + "x" * 32, encoding="utf-8")
        settings = MagicMock(url="http://127.0.0.1:8000", token_file=str(token))
        inventory = json.loads(
            ROOT.joinpath("tests/contracts/node-http-error-boundaries.json").read_text(
                encoding="utf-8"
            )
        )
        known = [
            (
                json.dumps({"error_category": code}).encode(),
                (
                    code
                    if code == "repository_cleanup_unverified"
                    else "source_discovery_failed"
                ),
            )
            for code in inventory["http_boundary_codes"]["source_handler"]
        ]
        for body, expected in [
            *known,
            *(
                (
                    b'{"error_category":"repository_cleanup_unverified","message":"PRIVATE"}',
                    "repository_cleanup_unverified",
                ),
                (
                    b'{"error_category":"repository_access_unavailable"}',
                    "source_discovery_failed",
                ),
                (b'{"error_category":"PRIVATE"}', "source_discovery_failed"),
                (
                    b'{"error_category":["repository_cleanup_unverified"]}',
                    "source_discovery_failed",
                ),
                (b"[]", "source_discovery_failed"),
                (b"invalid PRIVATE", "source_discovery_failed"),
                (b" " * 16385, "source_discovery_failed"),
            ),
        ]:
            response = io.BytesIO(body)
            error = urllib.error.HTTPError(
                "http://127.0.0.1", 400, "PRIVATE", {}, response
            )
            opener = MagicMock()
            opener.open.side_effect = error
            with (
                self.subTest(expected=expected, body_size=len(body)),
                patch(
                    "laomedo.skills.interface.sources.client.Settings",
                    return_value=settings,
                ),
                patch(
                    "laomedo.skills.interface.sources.client.urllib.request.build_opener",
                    return_value=opener,
                ),
                self.assertRaises(ValueError) as raised,
            ):
                source_request("discover", source="test")
            self.assertEqual(str(raised.exception), expected)
            self.assertNotIn("PRIVATE", str(raised.exception))
            self.assertTrue(response.closed)
        response = MagicMock()
        response.read.side_effect = OSError("PRIVATE")
        error = urllib.error.HTTPError("http://127.0.0.1", 400, "PRIVATE", {}, response)
        opener = MagicMock()
        opener.open.side_effect = error
        with (
            patch(
                "laomedo.skills.interface.sources.client.Settings",
                return_value=settings,
            ),
            patch(
                "laomedo.skills.interface.sources.client.urllib.request.build_opener",
                return_value=opener,
            ),
            self.assertRaisesRegex(ValueError, "source_discovery_failed"),
        ):
            source_request("discover", source="test")
        response.read.assert_called_once_with(16385)
        response.close.assert_called_once()
        response = MagicMock()
        response.read.return_value = (
            b'{"error_category":"repository_cleanup_unverified"}'
        )
        response.close.side_effect = OSError("PRIVATE")
        error = urllib.error.HTTPError("http://127.0.0.1", 400, "PRIVATE", {}, response)
        opener.open.side_effect = error
        with (
            patch(
                "laomedo.skills.interface.sources.client.Settings",
                return_value=settings,
            ),
            patch(
                "laomedo.skills.interface.sources.client.urllib.request.build_opener",
                return_value=opener,
            ),
            self.assertRaisesRegex(ValueError, "source_discovery_failed"),
        ):
            source_request("discover", source="test")
        response.close.assert_called_once()

    def test_source_coordinator_has_no_native_launcher_or_retired_private_methods(self):
        from laomedo.skills.sources.service import SkillSources

        for name in ("_git", "_repository", "_entries", "_blob", "_local_skills"):
            self.assertFalse(hasattr(SkillSources, name), name)
        for name in ("service", "repository", "local"):
            tree = ast.parse(
                ROOT.joinpath("src/laomedo/skills/sources", name + ".py").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(
                any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"Popen", "killpg"}
                    for node in ast.walk(tree)
                )
            )

    def test_independent_utility_bodies_preserve_original_literals_and_control_flow(
        self,
    ):
        record = json.loads(
            ROOT.joinpath("tests/contracts/skill-sources-64ac5fe.json").read_text(
                encoding="utf-8"
            )
        )
        with patch.object(sys, "path", [str(ROOT / "tools"), *sys.path]):
            contracts = runpy.run_path(
                str(ROOT / "tools/capture_interface_contracts.py")
            )
        aliases = {
            "_excluded": "excluded_parts",
            "_name": "skill_name",
            "_bundle": "validate_bundle",
            "_bundle_path": "validate_bundle_path",
        }
        baseline = ast.parse(record["utils_source"])
        module_aliases = {
            alias.asname
            for node in ast.walk(baseline)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.asname and alias.name.startswith("laomedo.")
        }
        for node in baseline.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in aliases:
                continue
            old_name = node.name
            node.name = aliases[node.name]
            node = contracts["normalize_body"](node, module_aliases)
            for item in ast.walk(node):
                if isinstance(item, ast.Name):
                    item.id = aliases.get(item.id, item.id)
            owner = "bundle" if old_name.startswith("_bundle") else "utils"
            current = ast.parse(
                ROOT.joinpath("src/laomedo/skills/sources", owner + ".py").read_text(
                    encoding="utf-8"
                )
            )
            actual = next(
                item
                for item in current.body
                if isinstance(item, ast.FunctionDef) and item.name == node.name
            )
            self.assertEqual(
                contracts["canonical_ast"](actual),
                contracts["canonical_ast"](node),
                old_name,
            )

    def test_utility_migration_is_explicit_flat_and_refuses_ambiguous_members(self):
        with patch.object(sys, "path", [str(ROOT / "tools/migrations"), *sys.path]):
            migration = runpy.run_path(
                str(ROOT / "tools/migrations/migrate_module_paths.py")
            )
        old = "laomedo.skills.sources.utils"
        for source in (
            f"from {old} import _bundle\nvalue=_bundle(files)\n",
            f"import {old} as old\nvalue=old._bundle(files)\n",
        ):
            migrated = migration["migrate_source"](source)
            self.assertIn("laomedo.skills.sources.bundle", migrated)
            self.assertIn("validate_bundle", migrated)
            self.assertEqual(migration["migrate_source"](migrated), migrated)
        for source in (
            f"from {old} import *\n",
            f"import {old} as old\nvalue=getattr(old,selected)\n",
        ):
            with self.assertRaises(migration["ManualMigrationRequired"]):
                migration["migrate_source"](source)
        for module in (
            "laomedo.skill_sources",
            "laomedo.skills.skill_sources",
            "laomedo.skills.sources.service",
        ):
            source = f"from {module} import SkillSources as Source\nvalue=Source._git(instance,cwd,args)\n"
            with self.assertRaises(migration["ManualMigrationRequired"]):
                migration["migrate_source"](source)

    def test_tracked_callers_do_not_import_retired_source_helpers(self):
        """Inspect executable imports/attributes and literal patch targets, not string fixtures."""
        paths = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "safe.directory=" + ROOT.as_posix(),
                    "-C",
                    str(ROOT),
                    "ls-files",
                    "-z",
                    "--",
                    "*.py",
                ]
            )
            .decode("utf-8")
            .split("\0")
        )
        old = "laomedo.skills.sources.utils"
        retired = {"_bundle", "_bundle_path", "_excluded", "_name"}
        for relative in filter(None, paths):
            tree = ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8-sig"))
            aliases = {
                alias.asname or alias.name: alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == old:
                    self.assertFalse(
                        retired & {alias.name for alias in node.names}, relative
                    )
                elif isinstance(node, ast.Attribute) and node.attr in retired:
                    self.assertNotEqual(
                        aliases.get(ast.unparse(node.value)), old, relative
                    )
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "patch"
                    and node.args
                ):
                    value = node.args[0]
                    if isinstance(value, ast.Constant):
                        self.assertNotIn(
                            value.value,
                            {old + "." + name for name in retired},
                            relative,
                        )
