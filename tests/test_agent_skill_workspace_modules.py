"""Internal controls for Agent-owned workspace helpers and preserved probes."""

import ast
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(ROOT / "tools/migrations"), *sys.path]):
    MIGRATION = runpy.run_path(str(ROOT / "tools/migrations/migrate_module_paths.py"))
RECORD = json.loads(
    (ROOT / "tests/contracts/agent-skill-workspace-6656c1c.json").read_text(
        encoding="utf-8"
    )
)


class AgentSkillWorkspaceModuleTests(unittest.TestCase):
    def test_all_five_function_bodies_and_signatures_are_unchanged(self):
        original = RECORD["baseline_source"]
        self.assertEqual(
            hashlib.sha256(original.encode()).hexdigest(), RECORD["source_sha256"]
        )
        self.assertEqual(
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "safe.directory=" + str(ROOT),
                    "show",
                    RECORD["base_revision"] + ":src/laomedo/skills/workspace/utils.py",
                ],
                cwd=ROOT,
            ).decode(),
            original,
        )
        original_nodes = {
            node.name: node
            for node in ast.parse(original).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(len(original_nodes), 5)
        for old, target in RECORD["symbols"].items():
            module, name = target.rsplit(".", 1)
            path = ROOT.joinpath("src", *module.split(".")).with_suffix(".py")
            current = next(
                node
                for node in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            self.assertEqual(ast.dump(original_nodes[name]), ast.dump(current), name)
            self.assertEqual(MIGRATION["SYMBOL_PATHS"][old], target)
            loaded = importlib.import_module(module)
            self.assertTrue(Path(loaded.__file__).is_relative_to(ROOT / "src"))
            self.assertTrue(callable(getattr(loaded, name)))

    def test_exception_code_arguments_and_inheritance_are_preserved(self):
        module = importlib.import_module("laomedo.agents.workspaces.skills.errors")
        original = next(
            node
            for node in ast.parse(RECORD["error_source"]).body
            if isinstance(node, ast.ClassDef)
        )
        current = next(
            node
            for node in ast.parse(
                Path(module.__file__).read_text(encoding="utf-8")
            ).body
            if isinstance(node, ast.ClassDef)
        )
        self.assertEqual(ast.dump(original), ast.dump(current))
        error = module.WorkspaceSkillError("materialized_skill_mismatch")
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.args, ("materialized_skill_mismatch",))
        self.assertEqual(error.code, "materialized_skill_mismatch")

    def test_known_split_symbols_migrate_and_ambiguous_namespaces_fail_closed(self):
        retired = (
            "laomedo.skills.workspace.utils",
            "laomedo.skills.workspace_skills",
            "laomedo.workspace_skills",
        )
        for old in retired:
            for source in (
                f"from {old} import initialize, remove_owned_tree, verify\n",
                f"import {old} as old\nold.verify(workspace, skills, evidence)\n",
            ):
                migrated = MIGRATION["migrate_source"](source)
                self.assertNotIn(old, migrated)
                compile(migrated, "<internal-import-migration>", "exec")
                self.assertEqual(MIGRATION["migrate_source"](migrated), migrated)
            for source in (
                f"from {old} import *\n",
                f"from {old} import unknown\n",
                f"import {old} as old\nvalue=old\n",
                f"import {old} as old\ngetattr(old, 'verify')(w,s,e)\n",
            ):
                with self.assertRaises(
                    MIGRATION["ManualMigrationRequired"], msg=source
                ):
                    MIGRATION["migrate_source"](source)
        with self.assertRaises(MIGRATION["ManualMigrationRequired"]):
            MIGRATION["migrate_source"](
                "from laomedo.local_runner import workspace_skills\n"
            )
        with self.assertRaises(MIGRATION["ManualMigrationRequired"]):
            MIGRATION["migrate_source"]("import laomedo.skills.workspace\n")

    def test_preserved_exp104_sources_allow_only_explicit_import_migration(self):
        for item in RECORD["retained_files"]:
            path = ROOT / item["path"]
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
            original = raw.decode("utf-8-sig")
            migrated = MIGRATION["migrate_source"](original)
            self.assertNotIn("import laomedo.skills.workspace.utils", migrated)
            self.assertIn("laomedo.agents.workspaces.skills.utils", migrated)
            compile(migrated, str(path) + "<internal-migration-only>", "exec")
            self.assertEqual(MIGRATION["migrate_source"](migrated), migrated)
            self.assertEqual(path.read_bytes(), raw)
            before = [
                ast.dump(
                    ast.Call(
                        func=ast.Name(id="verify", ctx=ast.Load()),
                        args=node.args,
                        keywords=node.keywords,
                    )
                )
                for node in ast.walk(ast.parse(original))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "workspace_skills"
                and node.func.attr == "verify"
            ]
            after = [
                ast.dump(
                    ast.Call(
                        func=ast.Name(id="verify", ctx=ast.Load()),
                        args=node.args,
                        keywords=node.keywords,
                    )
                )
                for node in ast.walk(ast.parse(migrated))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_migrated_workspace_skills_verify"
            ]
            self.assertEqual(len(before), 1, item["path"])
            self.assertEqual(before, after, item["path"])
            # The migration may replace imports and qualified symbol reads only.
            # It does not execute these historical native-provider probes.

    def test_maintained_imports_patch_targets_and_dependency_direction(self):
        """Guard static imports and bare literal patch calls, not dynamic Python."""
        self.assertFalse((ROOT / "src/laomedo/skills/workspace/utils.py").exists())
        self.assertFalse((ROOT / "src/laomedo/skills/workspace/errors.py").exists())
        preserved = {item["path"] for item in RECORD["retained_files"]}
        retired = "laomedo.skills.workspace"
        paths = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "safe.directory=" + str(ROOT),
                    "ls-files",
                    "-z",
                    "--",
                    "*.py",
                ],
                cwd=ROOT,
            )
            .decode()
            .split("\0")
        )
        for relative in filter(None, paths):
            path = ROOT / relative
            if relative in preserved or not path.is_file():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith(retired), relative)
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        any(item.name.startswith(retired) for item in node.names),
                        relative,
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "patch"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    self.assertFalse(node.args[0].value.startswith(retired), relative)
        for path in (ROOT / "src/laomedo/skills").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(
                        (node.module or "").startswith("laomedo.agents"), path
                    )
        for relative in ("baseline.py", "cleanup.py", "skills/utils.py"):
            tree = ast.parse(
                (ROOT / "src/laomedo/agents/workspaces" / relative).read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(
                any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
            )
            self.assertTrue(
                any(
                    isinstance(node, ast.ImportFrom)
                    and node.module == "__future__"
                    and any(item.name == "annotations" for item in node.names)
                    for node in tree.body
                )
            )


if __name__ == "__main__":
    unittest.main()
