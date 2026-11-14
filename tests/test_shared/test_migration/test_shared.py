"""Current Shared symbol owners and explicit historical-evidence integrity."""

from support.paths import repository_root
from test_shared.test_migration.utils import load_owner_maps

import ast
import importlib
import json
import unittest
from unittest.mock import patch

from support.retained import load_retained_shared, refuse_private_git_api

ROOT = repository_root()
migration = load_owner_maps()


class SharedMigrationTests(unittest.TestCase):
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
        for prefix in (
            "laomedo.skills.",
            "laomedo.agents.workspaces.skills.",
            "laomedo.host.publication.ingestion.",
        ):
            with self.subTest(prefix=prefix):
                self.assertTrue(any(target.startswith(prefix) for target in targets))
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
            if target.startswith(("laomedo.git.", "laomedo.host.http."))
        }
        self.assertTrue(targets)
        for target in targets:
            with self.subTest(target=target):
                owner, name = target.rsplit(".", 1)
                self.assertTrue(hasattr(importlib.import_module(owner), name), target)

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
