"""One-pass Shared migration and explicit refusal controls, not live acceptance."""

from support.paths import repository_root
from test_shared.test_migration.utils import load_migration

import ast
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from support.retained import load_retained_shared, refuse_private_git_api

ROOT = repository_root()
TOOL = ROOT / "tools/migrations/migrate_module_paths.py"
migration = load_migration()


class SharedMigrationTests(unittest.TestCase):
    def test_registry_split_symbols_and_ambiguous_module_values(self):
        old = "laomedo.skills.registry.utils"
        for source in (
            f"from {old} import inventory, tree_hash\nvalue = tree_hash(inventory(root))\n",
            f"import {old} as old\nvalue = old.inventory(root)\n",
            "from laomedo.skills.registry import utils as old\nvalue = old.tree_hash(files)\n",
        ):
            rewritten = migration.migrate_source(source)
            self.assertNotIn(old, rewritten)
            compile(rewritten, "<registry-migration>", "exec")
            self.assertEqual(migration.migrate_source(rewritten), rewritten)
        for source in (
            f"from {old} import *\n",
            f"from {old} import unknown\n",
            f"import {old}\n",
            f"import {old} as old\nvalue = old.unknown(root)\n",
            f"import {old} as old\nvalue = getattr(old, 'inventory')(root)\n",
            f"import {old} as old\nvalue = old\n",
        ):
            with (
                self.subTest(source=source),
                self.assertRaises(migration.ManualMigrationRequired),
            ):
                migration.migrate_source(source)

    def test_partial_source_settings_keep_constants_and_move_only_settings(self):
        old = "laomedo.skills.sources.settings"
        new = "laomedo.skills.interface.sources.settings"
        for source in (
            f"from {old} import Settings\nvalue = Settings()\n",
            f"import {old} as settings\nvalue = settings.Settings()\n",
            "from laomedo.skills.sources import settings\nvalue = settings.Settings()\n",
            f"from {old} import Settings, SKIP\nvalue = (Settings(), SKIP)\n",
        ):
            rewritten = migration.migrate_source(source)
            self.assertIn(new, rewritten)
            self.assertEqual(migration.migrate_source(rewritten), rewritten)
            if "Settings, SKIP" in source:
                self.assertIn(f"from {old} import SKIP", rewritten)
                self.assertIn(f"from {new} import Settings", rewritten)
        for source in (
            f"from {old} import *\n",
            f"import {old} as settings\nvalue = getattr(settings, 'Settings')\n",
            f"import {old} as settings\nvalue = getattr(settings, selected)\n",
            f"import {old}\nvalue = {old}.Settings()\n",
        ):
            with (
                self.subTest(source=source),
                self.assertRaises(migration.ManualMigrationRequired),
            ):
                migration.migrate_source(source)
        for source in (
            f"from {old} import SKIP\nvalue = SKIP\n",
            f"import {old} as settings\nvalue = settings.MAX_ENTRIES\n",
            f"import {old} as settings\nvalue = getattr(settings, 'SKIP')\n",
        ):
            self.assertEqual(migration.migrate_source(source), source)

    def test_server_import_paths_and_launch_commands_have_distinct_owners(self):
        for owner, feature in (
            ("skills", "sources"),
            ("skills", "operations"),
        ):
            old = f"laomedo.{owner}.{feature}.server"
            server = f"laomedo.{owner}.interface.{feature}.server"
            cli = f"laomedo.{owner}.interface.{feature}.cli"
            self.assertEqual(migration.MODULE_PATHS[old], server)
            self.assertEqual(migration.CLI_PATHS[old], cli)
            rewritten = migration.migrate_source("python -m " + old + " --help")
            self.assertIn("-m " + cli + " --help", rewritten)
            self.assertEqual(migration.migrate_source(rewritten), rewritten)

    def test_skill_relocation_targets_resolve_to_declared_definitions(self):
        targets = {
            target
            for target in migration.SYMBOL_PATHS.values()
            if target.startswith(
                (
                    "laomedo.skills.",
                    "laomedo.agents.workspace.skills.",
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
            "import laomedo.github.transport.git.utils as native\nnative._base_git_environment()\n",
            "from laomedo.github_git_transport import _credential_environment\n",
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(
                    migration.ManualMigrationRequired, "manual migration|manual|Use Git"
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

    def test_historical_native_entrypoints_still_refuse_before_process_work(self):
        module = load_retained_shared("experiments.exp104.native_managed_probe")
        self.assertIs(module._base_git_environment, refuse_private_git_api)
        with patch.object(module.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Historical experiment"):
                module.git("status")
            run.assert_not_called()

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
