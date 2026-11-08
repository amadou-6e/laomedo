"""Keep GitHub boundaries discoverable without compatibility facades."""

import ast
import importlib
import sys
import unittest
from unittest.mock import Mock, patch

from support.paths import repository_root
from support.model_contracts import assert_described_models
from laomedo.github.transport.mediated import GitHubMediatedTransport

ROOT = repository_root()


class GitHubOwnershipTests(unittest.TestCase):

    def test_github_records_keep_described_fields(self):
        assert_described_models(
            "github.models", "github.issues.models", "github.pull_requests.models"
        )

    def test_github_core_does_not_import_graph_frameworks(self):
        paths = list((ROOT / "src/laomedo/github").rglob("*.py"))
        self.assertTrue(paths, "GitHub dependency scan must not be empty")
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                names = (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                )
                for name in names:
                    self.assertFalse(
                        name == "lfx"
                        or name.startswith("lfx.")
                        or name == "laomedo.work_graph"
                        or name.startswith("laomedo.work_graph."),
                        (path, node.lineno, name),
                    )

    def test_files_have_cohesive_definitions_and_no_nested_classes(self):
        for path in (ROOT / "src/laomedo/github").rglob("*.py"):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
                functions = [
                    n
                    for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                self.assertFalse(classes and functions)
                self.assertEqual(
                    sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree)),
                    len(classes),
                )
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        self.assertFalse(
                            any(i.name.startswith("laomedo.") for i in n.names),
                            str(path),
                        )
        for relative in (
            "interface",
            "interface/issues",
            "interface/pull_requests",
            "issues",
            "pull_requests",
            "transport",
            "transport/git",
            "transport/rest",
            "workflows",
        ):
            self.assertTrue(
                (ROOT / "src/laomedo/github" / relative / "README.md").is_file()
            )

    def test_retired_definitions_are_absent_and_migrate_to_final_owners(self):
        migration = load_migration()
        for feature in ("issues", "pull_requests"):
            for name in ("client", "server", "settings", "cli"):
                old = f"laomedo.github.{feature}.{name}"
                self.assertFalse(
                    ROOT.joinpath("src", *old.split(".")).with_suffix(".py").exists()
                )
                self.assertEqual(
                    migration.MODULE_PATHS[old],
                    f"laomedo.github.interface.{feature}.{name}",
                )
        source = "from laomedo.github.issues.utils import fetch_context\nfrom laomedo.github.transport.git.transport import GitHubMediatedTransport\n"
        migrated = migration.migrate_source(source)
        self.assertIn(
            "from laomedo.github.issues.context_reader import fetch_context", migrated
        )
        self.assertIn(
            "from laomedo.github.transport.mediated import GitHubMediatedTransport",
            migrated,
        )
        self.assertEqual(migration.migrate_source(migrated), migrated)
        moved_main = migration.migrate_source(
            "from laomedo.github.issues.utils import main\n"
        )
        self.assertIn("from laomedo.github.issues.context import main", moved_main)
        self.assertEqual(migration.migrate_source(moved_main), moved_main)

        # The loader enforces equality of the full non-import AST on every load.
        # Its existing tamper/refusal controls remain in test_shared.

    def test_dispatcher_preserves_exact_payload_binding_and_uncertain_exception(self):
        git, rest = Mock(repository="owner/repo"), Mock(repository="owner/repo")
        transport = GitHubMediatedTransport(git, rest)
        payload, binding = {"a": 1}, object()
        for operation, target in (
            ("git_push", git),
            ("git_fetch", git),
            ("pr_node_read", rest),
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
            self.assertIs(target.call_args.args[2], payload)
            self.assertIs(target.call_args.kwargs["verified_stage"], binding)
        uncertain = RuntimeError("outcome unknown")
        rest.side_effect = uncertain
        with self.assertRaises(RuntimeError) as caught:
            transport("owner/repo", "pr_node_update", payload)
        self.assertIs(caught.exception, uncertain)
        with self.assertRaisesRegex(ValueError, "repository_mismatch"):
            GitHubMediatedTransport(git, Mock(repository="another/repo"))

    def test_interface_cli_and_context_cli_own_their_actual_entrypoints(self):
        for name in ("issues", "pull_requests"):
            module = importlib.import_module(f"laomedo.github.interface.{name}.cli")
            self.assertEqual(module.main.__module__, module.__name__)
            with patch.object(sys, "argv", ["service", "--help"]), patch("sys.stdout"):
                with self.assertRaises(SystemExit) as caught:
                    module.main()
            self.assertEqual(caught.exception.code, 0)
        context = importlib.import_module("laomedo.github.issues.context")
        self.assertEqual(context.main.__module__, context.__name__)

    def test_production_contract_tests_have_no_campaign_import_dependency(self):
        paths = list((ROOT / "tests/test_github").rglob("test_*.py"))
        self.assertTrue(paths, "Scan the actual GitHub regression owner")
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                with self.subTest(path=path.relative_to(ROOT), line=node.lineno):
                    self.assertFalse(
                        any(
                            module == "experiments"
                            or module.startswith("experiments.")
                            or module == "support.retained"
                            for module in modules
                        )
                    )
