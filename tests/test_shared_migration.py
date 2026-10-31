"""One-pass Shared migration and explicit refusal controls, not live acceptance."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from retained_shared import load_retained_shared, refuse_private_git_api

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/migrations/migrate_module_paths.py"
sys.path.insert(0, str(TOOL.parent))
SPEC = importlib.util.spec_from_file_location("shared_migration_controls", TOOL)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class SharedMigrationTests(unittest.TestCase):
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
                "from laomedo.skills.sources.transport import NoRedirect\n",
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
