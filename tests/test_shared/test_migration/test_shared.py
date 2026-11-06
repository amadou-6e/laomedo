"""One-pass Shared migration and explicit refusal controls, not live acceptance."""

from support.paths import repository_root
from test_shared.test_migration.utils import load_migration

import ast
import importlib
import json
from pathlib import Path
import unittest

ROOT = repository_root()
TOOL = ROOT / "tools/migrations/migrate_module_paths.py"
migration = load_migration()


class SharedMigrationTests(unittest.TestCase):
    def test_workspace_split_symbols_and_ambiguous_namespaces(self):
        for old in (
            "laomedo.skills.workspace.utils",
            "laomedo.skills.workspace_skills",
            "laomedo.workspace_skills",
        ):
            for source in (
                f"from {old} import initialize, remove_owned_tree, verify\n",
                f"import {old} as old\nold.verify(workspace, skills, evidence)\n",
            ):
                rewritten = migration.migrate_source(source)
                self.assertNotIn(old, rewritten)
                compile(rewritten, "<workspace-migration>", "exec")
                self.assertEqual(migration.migrate_source(rewritten), rewritten)
            for source in (
                f"from {old} import *\n",
                f"from {old} import unknown\n",
                f"import {old} as old\nvalue = old\n",
                f"import {old} as old\ngetattr(old, 'verify')(w, s, e)\n",
            ):
                with (
                    self.subTest(source=source),
                    self.assertRaises(migration.ManualMigrationRequired),
                ):
                    migration.migrate_source(source)
        for source in (
            "from laomedo.local_runner import workspace_skills\n",
            "import laomedo.skills.workspace\n",
        ):
            with (
                self.subTest(source=source),
                self.assertRaises(migration.ManualMigrationRequired),
            ):
                migration.migrate_source(source)
        current = "import laomedo.agents.workspaces.skills\n"
        self.assertEqual(migration.migrate_source(current), current)

    def test_automatic_targets_have_current_owners_and_no_manual_contract(self):
        self.assertTrue(migration.MODULE_PATHS)
        self.assertTrue(migration.SYMBOL_PATHS)
        self.assertFalse(set(migration.SYMBOL_PATHS) & set(migration.MANUAL_SYMBOLS))
        for target in set(migration.MODULE_PATHS.values()) | set(
            migration.SYMBOL_PATHS.values()
        ):
            with self.subTest(target=target):
                path = ROOT.joinpath("src", *target.split("."))
                if (
                    path.with_suffix(".py").is_file()
                    or (path / "__init__.py").is_file()
                ):
                    continue
                owner = path.parent
                self.assertTrue(
                    owner.with_suffix(".py").is_file()
                    or (owner / "__init__.py").is_file(),
                    target,
                )

    def test_automatic_symbols_are_declared_and_not_shadowed_by_manual_prefixes(self):
        cache = {}
        for key, target in migration.SYMBOL_PATHS.items():
            with self.subTest(symbol=key):
                self.assertFalse(
                    any(
                        key == manual or key.startswith(manual + ".")
                        for manual in migration.MANUAL_SYMBOLS
                    )
                )
                direct = ROOT.joinpath("src", *target.split("."))
                if (
                    direct.with_suffix(".py").is_file()
                    or (direct / "__init__.py").is_file()
                ):
                    continue
                owner, name = target.rsplit(".", 1)
                path = ROOT.joinpath("src", *owner.split(".")).with_suffix(".py")
                if not path.is_file():
                    path = ROOT.joinpath("src", *owner.split("."), "__init__.py")
                if path not in cache:
                    names = set()
                    for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
                        if isinstance(
                            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                        ):
                            names.add(node.name)
                        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                            for assigned in (
                                node.targets
                                if isinstance(node, ast.Assign)
                                else [node.target]
                            ):
                                names.update(
                                    item.id
                                    for item in ast.walk(assigned)
                                    if isinstance(item, ast.Name)
                                )
                        elif isinstance(node, (ast.Import, ast.ImportFrom)):
                            names.update(
                                item.asname or item.name.split(".")[0]
                                for item in node.names
                            )
                    cache[path] = names
                self.assertIn(name, cache[path], target)

    def test_fully_qualified_injection_calls_and_expanded_keywords_refuse(self):
        for owner, symbol in (
            ("laomedo.github.transport.git.transport", "GitHubGitTransport"),
            ("laomedo.github_git_transport", "GitHubGitTransport"),
            ("laomedo.host.publication.verified.git", "VerifiedGitStage"),
            ("laomedo.verified_git_stage", "VerifiedGitStage"),
            ("laomedo.host.publication.verified.utils", "stage_verified_git"),
            ("laomedo.verified_git_stage", "stage_verified_git"),
        ):
            for arguments in ("run=callback", "**options"):
                source = f"import {owner}\n{owner}.{symbol}({arguments})\n"
                with (
                    self.subTest(source=source),
                    self.assertRaisesRegex(migration.ManualMigrationRequired, "run="),
                ):
                    migration.migrate_source(source)

    def test_skill_relocation_targets_resolve_to_declared_definitions(self):
        targets = {
            target
            for target in migration.SYMBOL_PATHS.values()
            if target.startswith(
                (
                    "laomedo.skills.",
                    "laomedo.agents.workspaces.skills.",
                    "laomedo.host.publication.ingestion.",
                )
            )
        }
        self.assertTrue(targets)
        for target in targets:
            with self.subTest(target=target):
                target_path = ROOT.joinpath("src", *target.split("."))
                if (
                    target_path.with_suffix(".py").is_file()
                    or (target_path / "__init__.py").is_file()
                ):
                    continue  # A migrated module import names the module itself.
                owner, name = target.rsplit(".", 1)
                path = ROOT.joinpath("src", *owner.split(".")).with_suffix(".py")
                self.assertTrue(path.is_file(), target)
                definitions = set()
                for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    ):
                        definitions.add(node.name)
                    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                        for assigned in (
                            node.targets
                            if isinstance(node, ast.Assign)
                            else [node.target]
                        ):
                            definitions.update(
                                item.id
                                for item in ast.walk(assigned)
                                if isinstance(item, ast.Name)
                            )
                self.assertIn(name, definitions, target)

    def test_every_shared_symbol_target_resolves_to_its_defining_module(self):
        targets = {
            target
            for target in migration.SYMBOL_PATHS.values()
            if target.startswith(("laomedo.git.", "laomedo.http."))
        }
        self.assertTrue(targets)
        for target in targets:
            with self.subTest(target=target):
                owner, name = target.rsplit(".", 1)
                self.assertTrue(hasattr(importlib.import_module(owner), name), target)

    def test_retired_helpers_refuse_direct_and_aliased_source(self):
        for source in (
            "from laomedo.agents.workspace.git import _bounded_git as execute\n",
            "from laomedo.git_workspace import prepare_git_workspace\n",
            "from laomedo.agents.workspaces.git import _bounded_git\n",
            "import laomedo.github_git_transport as git\ngit._run_bounded_tree(args)\n",
            "from laomedo.github.transport.git import utils as u\nu._run_bounded_tree(args)\n",
            "from laomedo.github.transport import git as g\ng.utils._run_bounded_tree(args)\n",
            "import laomedo.github.transport.git.utils as native\nnative._base_git_environment()\n",
            "from laomedo.github_git_transport import _credential_environment\n",
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(
                    migration.ManualMigrationRequired,
                    "manual migration|manual|Use (?:Git|AgentWorkspace)",
                ):
                    migration.migrate_source(source)

    def test_all_three_changed_injection_signatures_refuse_automatic_rewrite(self):
        for owner, name in (
            ("laomedo.github.transport.git.transport", "GitHubGitTransport"),
            ("laomedo.host.publication.verified.git", "VerifiedGitStage"),
            ("laomedo.host.publication.verified.utils", "stage_verified_git"),
        ):
            for source in (
                f"from {owner} import {name} as Factory\nFactory(run=callback)\n",
                f"import {owner} as module\nmodule.{name}(run=callback)\n",
            ):
                with self.subTest(source=source):
                    with self.assertRaisesRegex(
                        migration.ManualMigrationRequired, "run="
                    ):
                        migration.migrate_source(source)

    def test_timeout_and_redirect_migration_are_one_pass(self):
        for source, target in (
            (
                "from laomedo.github.transport.git.transport import GitTreeTimeout\n",
                "laomedo.git.errors",
            ),
            (
                "from laomedo.http.redirect import NoRedirect\n",
                "laomedo.http.redirect",
            ),
            (
                "from laomedo.github.transport.rest.transport import _NoRedirect\n",
                "laomedo.http.redirect",
            ),
        ):
            with self.subTest(source=source):
                rewritten = migration.migrate_source(source)
                self.assertIn(target, rewritten)
                self.assertEqual(migration.migrate_source(rewritten), rewritten)

    def test_inventory_preserves_original_bytes_and_defines_no_runtime_facade(self):
        from hashlib import sha256

        inventory = json.loads(
            (ROOT / "tools/migrations/retained-shared-callers.json").read_text()
        )
        for record in inventory["files"]:
            with self.subTest(path=record["path"]):
                self.assertEqual(
                    sha256((ROOT / record["path"]).read_bytes()).hexdigest(),
                    record["sha256"],
                )
        source = ROOT / "src/laomedo"
        for path in (source / "git").rglob("*.py"):
            self.assertNotIn("retained_shared", path.read_text(encoding="utf-8"))
