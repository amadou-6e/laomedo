"""D4 ownership/contract controls; no native GitHub or Agent acceptance."""

import ast
from hashlib import sha256
import importlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from laomedo.github.contract import (
    issue_digest,
    labels_value,
    repository_from_url,
    validate_repository,
)
from laomedo.github.issues.errors import IssueContextError
from laomedo.github.pull_requests.contract import pr_digest
from laomedo.github.transport.mediated import GitHubMediatedTransport
from retained_github import load_retained_github

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(Path(ROOT, "tools/migrations")), *sys.path]):
    MIGRATION = runpy.run_path(
        str(Path(ROOT, "tools/migrations/migrate_module_paths.py"))
    )


class GitHubOwnershipTests(unittest.TestCase):
    """Check actual moved boundaries and flat migration without live dispatch."""

    def test_shared_admission_keeps_distinct_case_and_error_contracts(self):
        self.assertEqual(validate_repository("Owner/RePo"), ("Owner", "RePo"))
        self.assertEqual(
            repository_from_url("https://github.com/Owner/RePo/"), "owner/repo"
        )
        with self.assertRaisesRegex(ValueError, "^Repository must be owner/name$"):
            validate_repository("owner/../repo")
        for value in (None, "http://github.com/o/r", "https://github.com/o/r?q=1"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "^repository_url_invalid$"),
            ):
                repository_from_url(value)
        labels = ["z", "é"]
        self.assertEqual(labels_value(labels), ["z", "é"])
        self.assertEqual(labels, ["z", "é"])
        for value in (["a", "a"], [""], "label"):
            with self.assertRaisesRegex(ValueError, "^labels_invalid$"):
                labels_value(value)

    def test_pr_digest_is_the_canonical_function_and_unicode_preimage(self):
        contract = importlib.import_module("laomedo.github.pull_requests.contract")
        self.assertIs(pr_digest, issue_digest)
        self.assertIs(contract.pr_digest, issue_digest)
        value = {"title": "λ é", "labels": ["café"], "body": None}
        expected = (
            "sha256:"
            + sha256(
                '{"body":null,"labels":["café"],"title":"λ é"}'.encode()
            ).hexdigest()
        )
        self.assertEqual(pr_digest(value), expected)
        self.assertEqual(
            MIGRATION["SYMBOL_PATHS"][
                "laomedo.github.pull_requests.contract.pr_digest"
            ],
            "laomedo.github.contract.issue_digest",
        )

    def test_dispatcher_forwards_exact_objects_and_preserves_outcomes(self):
        git, rest = Mock(repository="owner/repo"), Mock(repository="owner/repo")
        transport = GitHubMediatedTransport(git, rest)
        payload, binding = {"a": 1}, object()
        for operation, target in (
            ("git_push", git),
            ("git_fetch", git),
            ("create_pr", rest),
            ("unknown", rest),
        ):
            self.assertIs(
                transport("owner/repo", operation, payload, verified_stage=binding),
                target.return_value,
            )
            target.assert_called_with(
                "owner/repo", operation, payload, verified_stage=binding
            )
        failure = RuntimeError("uncertain")
        rest.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            transport("owner/repo", "create_pr", payload)
        self.assertIs(caught.exception, failure)
        with self.assertRaisesRegex(ValueError, "^repository_mismatch$"):
            GitHubMediatedTransport(git, Mock(repository="other/repo"))

    def test_context_cli_main_and_module_guard_still_run_the_reader(self):
        for outcome, status in (
            ({"issue": {"number": 7}}, 0),
            (IssueContextError("issue_unavailable"), 2),
        ):
            output = io.StringIO()
            with (
                patch(
                    "laomedo.github.issues.context_reader.fetch_context",
                    side_effect=outcome if isinstance(outcome, Exception) else None,
                    return_value=outcome,
                ) as reader,
                patch.object(
                    sys, "argv", ["context", "Owner/Repo", "7", "--target-pr", "9"]
                ),
                patch("sys.stdout", output),
                self.assertRaises(SystemExit) as caught,
            ):
                runpy.run_module("laomedo.github.issues.context", run_name="__main__")
            self.assertEqual(caught.exception.code, status)
            reader.assert_called_once_with("Owner/Repo", 7, supplied_target_pr=9)
            self.assertEqual(
                json.loads(output.getvalue()),
                {"error": "issue_unavailable"} if status else outcome,
            )

    def test_migration_preserves_aliases_and_refuses_unknown_split_members(self):
        cases = {
            "from laomedo.github.issues.utils import fetch_context as read\nx=read(repo,7)\n": "from laomedo.github.issues.context_reader import fetch_context as read",
            "from laomedo.github.issues.utils import main\nx=main()\n": "from laomedo.github.issues.context import main",
            "import laomedo.github.issues.utils as old\nx=old.fetch_context(repo,7)\n": "laomedo.github.issues.context_reader",
            "from laomedo.github.transport.git.transport import GitHubMediatedTransport\n": "from laomedo.github.transport.mediated import GitHubMediatedTransport",
            "from laomedo.work_graph.github import validate_repository\n": "from laomedo.github.contract import validate_repository",
        }
        for source, expected in cases.items():
            migrated = MIGRATION["migrate_source"](source)
            self.assertIn(expected, migrated)
            self.assertEqual(MIGRATION["migrate_source"](migrated), migrated)
        for source in (
            "from laomedo.github.issues.utils import *\n",
            "import laomedo.github.issues.utils as old\nx=getattr(old,name)\n",
        ):
            with self.assertRaises(MIGRATION["ManualMigrationRequired"]):
                MIGRATION["migrate_source"](source)

    def test_retained_probe_bytes_and_loader_scope_are_explicit(self):
        manifest = json.loads(
            Path(ROOT, "tools/migrations/retained-github-callers.json").read_text()
        )
        self.assertEqual(len(manifest["files"]), 6)
        for record in manifest["files"]:
            self.assertEqual(
                sha256(Path(ROOT, record["path"]).read_bytes()).hexdigest(),
                record["sha256"],
            )
        with self.assertRaisesRegex(ValueError, "not an explicitly retained"):
            load_retained_github("laomedo.github.issues.context_reader")
        module = load_retained_github("experiments.exp100.probe_native_capture")
        self.assertIs(module.GitHubMediatedTransport, GitHubMediatedTransport)

    def test_current_producers_keep_catalogue_and_cli_only_errors_distinct(self):
        catalogue = json.loads(
            Path(
                ROOT, "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        entries = catalogue.get("errors", catalogue)
        self.assertTrue({"repository_url_invalid", "labels_invalid"} <= set(entries))
        # Context argument prose remains a CLI contract, not an invented node code.
        self.assertNotIn("Repository must be owner/name", entries)

    def test_retired_context_file_and_core_dependency_cannot_return(self):
        self.assertFalse(Path(ROOT, "src/laomedo/github/issues/utils.py").exists())
        shared = Path(ROOT, "src/laomedo/github/contract.py").read_text()
        reader = Path(ROOT, "src/laomedo/github/issues/context_reader.py").read_text()
        self.assertNotIn("laomedo.work_graph", shared + reader)
        self.assertNotIn("lfx", shared + reader)
        self.assertNotIn(
            "class GitHubMediatedTransport",
            Path(ROOT, "src/laomedo/github/transport/git/transport.py").read_text(),
        )
        paths = [
            *Path(ROOT, "src/laomedo/github").rglob("*.py"),
            Path(ROOT, "src/laomedo/integrations/langflow/viewer.py"),
        ]
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        any(alias.name.startswith("laomedo.") for alias in node.names),
                        str(path),
                    )

    def test_maintained_executable_imports_use_current_definitions(self):
        tracked = (
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
            .decode()
            .split("\0")
        )
        retired_symbols = {
            "laomedo.github.issues.contract": {
                "repository_from_url",
                "labels_value",
                "issue_digest",
            },
            "laomedo.github.transport.git.transport": {"GitHubMediatedTransport"},
            "laomedo.work_graph.github": {"validate_repository"},
        }
        for relative in filter(None, tracked):
            path = Path(ROOT, relative)
            if not path.exists() or relative.startswith("experiments/"):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(
                        node.module, "laomedo.github.issues.utils", relative
                    )
                    self.assertFalse(
                        {alias.name for alias in node.names}
                        & retired_symbols.get(node.module, set()),
                        relative,
                    )
