"""Registry ownership, exact byte behavior and saved-consumer contracts."""

import ast
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from laomedo.skills.registry.files import inventory, read_json, write_json
from laomedo.skills.registry.hashing import canonical_json, tree_hash
from laomedo.skills.registry.paths import validate_relative_path
from laomedo.skills.registry.errors import SkillStoreError

ROOT = Path(__file__).resolve().parents[1]
RETIRED = "laomedo.skills.registry.utils"
with patch.object(sys, "path", [str(Path(ROOT, "tools/migrations")), *sys.path]):
    MIGRATION = runpy.run_path(
        str(Path(ROOT, "tools/migrations/migrate_module_paths.py"))
    )


class RegistryModuleTests(unittest.TestCase):
    def test_registry_symbol_map_targets_are_callable(self):
        """Saved consumers resolve each supported registry helper to its owner."""
        expected = {
            "_safe_name": "laomedo.skills.registry.paths.validate_name",
            "_safe_relative": "laomedo.skills.registry.paths.validate_relative_path",
            "_is_link": "laomedo.skills.registry.files.is_link",
            "inventory": "laomedo.skills.registry.files.inventory",
            "_write_json": "laomedo.skills.registry.files.write_json",
            "_read_json": "laomedo.skills.registry.files.read_json",
            "_hash": "laomedo.skills.registry.hashing.hash_bytes",
            "_canonical_json": "laomedo.skills.registry.hashing.canonical_json",
            "tree_hash": "laomedo.skills.registry.hashing.tree_hash",
            "file_hashes": "laomedo.skills.registry.hashing.file_hashes",
            "validate_policy": "laomedo.skills.registry.policy.validate_policy",
            "validate_draft": "laomedo.skills.registry.policy.validate_draft",
            "patch_for": "laomedo.skills.registry.diff.patch_for",
        }
        for name, target in expected.items():
            self.assertEqual(MIGRATION["SYMBOL_PATHS"][RETIRED + "." + name], target)
            module, symbol = target.rsplit(".", 1)
            self.assertTrue(callable(getattr(importlib.import_module(module), symbol)))

    def test_split_module_migration_supports_known_symbols_and_refuses_ambiguity(self):
        self.assertFalse(Path(ROOT, "src/laomedo/skills/registry/utils.py").exists())
        source = f"from {RETIRED} import inventory, tree_hash\nresult=tree_hash(inventory(root))\n"
        migrated = MIGRATION["migrate_source"](source)
        self.assertIn("from laomedo.skills.registry.files import inventory", migrated)
        self.assertIn("from laomedo.skills.registry.hashing import tree_hash", migrated)
        self.assertEqual(MIGRATION["migrate_source"](migrated), migrated)
        for source in (
            f"from {RETIRED} import *\n",
            f"from {RETIRED} import unknown\n",
            f"import {RETIRED}\n",
            f"import {RETIRED} as old\nvalue=old.unknown(root)\n",
            f"import {RETIRED} as old\nvalue=getattr(old, 'inventory')(root)\n",
            f"import {RETIRED} as old\nvalue=old\n",
        ):
            with self.assertRaises(MIGRATION["ManualMigrationRequired"], msg=source):
                MIGRATION["migrate_source"](source)
        for source in (
            f"import {RETIRED} as old\nvalue=old.inventory(root)\n",
            "from laomedo.skills.registry import utils as old\nvalue=old.tree_hash(files)\n",
        ):
            migrated = MIGRATION["migrate_source"](source)
            self.assertNotIn(RETIRED, migrated)
            compile(migrated, "<migrated>", "exec")

    def test_maintained_callers_have_no_retired_registry_imports(self):
        retained = json.loads(
            Path(ROOT, "tools/migrations/retained-registry-callers.json").read_text()
        )["files"]
        preserved = {item["path"]: item["sha256"] for item in retained}
        tracked = (
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
        for relative in filter(None, tracked):
            path = Path(ROOT, relative)
            if not path.exists():
                continue  # The deleted utility is guarded explicitly above.
            if relative in preserved:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), preserved[relative]
                )
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, RETIRED, (relative, node.lineno))
                    if node.module == "laomedo.skills.registry":
                        self.assertNotIn(
                            "utils", {item.name for item in node.names}, relative
                        )
                    if node.module in {
                        "laomedo.skills.workspace.utils",
                        "laomedo.agents.workspaces.skills.utils",
                    }:
                        self.assertNotIn(
                            "_is_link", {item.name for item in node.names}, relative
                        )
                elif isinstance(node, ast.Import):
                    self.assertNotIn(
                        RETIRED, {item.name for item in node.names}, relative
                    )
                elif (
                    isinstance(node, ast.Call)
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    name = (
                        node.func.id
                        if isinstance(node.func, ast.Name)
                        else (
                            node.func.attr
                            if isinstance(node.func, ast.Attribute)
                            else ""
                        )
                    )
                    if name in {"import_module", "__import__", "patch"}:
                        self.assertNotEqual(
                            node.args[0].value,
                            "laomedo.skills.workspace.utils._is_link",
                            (relative, node.lineno),
                        )
                        self.assertNotEqual(
                            node.args[0].value,
                            "laomedo.agents.workspaces.skills.utils._is_link",
                            (relative, node.lineno),
                        )
                        self.assertFalse(
                            node.args[0].value == RETIRED
                            or node.args[0].value.startswith(RETIRED + "."),
                            (relative, node.lineno),
                        )
        for item in retained:
            raw = Path(ROOT, item["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
        ci = Path(ROOT, ".github/workflows/work-graph.yml").read_text()
        self.assertIn("python tools/run_retained_exp08.py test", ci)
        self.assertIn("python tools/run_retained_exp08.py probe", ci)

    def test_function_leaves_and_models_have_distinct_owners(self):
        for name in ("paths", "files", "hashing", "policy", "diff"):
            path = Path(ROOT, "src/laomedo/skills/registry", name + ".py")
            tree = ast.parse(path.read_text())
            self.assertFalse(
                any(isinstance(node, ast.ClassDef) for node in ast.walk(tree)), name
            )
            self.assertFalse(
                any(
                    isinstance(node, ast.Import)
                    and any(item.name.startswith("laomedo.") for item in node.names)
                    for node in ast.walk(tree)
                ),
                name,
            )
        for name in ("store", "models", "errors"):
            tree = ast.parse(
                Path(ROOT, "src/laomedo/skills/registry", name + ".py").read_text()
            )
            self.assertFalse(
                any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for node in tree.body
                ),
                name,
            )
        tool = ast.parse(
            Path(ROOT, "tools/run_retained_exp08.py").read_text(encoding="utf-8-sig")
        )
        self.assertFalse(any(isinstance(node, ast.ClassDef) for node in ast.walk(tool)))

    def test_policy_canonicalization_and_tree_hashes_keep_exact_bytes(self):
        value = {"unicode": "\u00e9", "flag": False, "extra": [1, None]}
        self.assertEqual(
            canonical_json(value),
            b'{"extra":[1,null],"flag":false,"unicode":"\\u00e9"}',
        )
        revisions = {
            tree_hash({"SKILL.md": data}) for data in (b"one\n", b"one\r\n", b"one")
        }
        self.assertEqual(len(revisions), 3)
        with self.assertRaises(SkillStoreError) as raised:
            validate_relative_path("../SKILL.md")
        self.assertEqual(raised.exception.code, "unsafe_relative_path")
        self.assertEqual(raised.exception.args, ("unsafe_relative_path",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(SkillStoreError, "missing_skill_file"):
                inventory(root)
            path = Path(root, "record.json")
            write_json(path, {"z": 1, "a": None})
            self.assertEqual(path.read_bytes(), b'{\n  "a": null,\n  "z": 1\n}\n')
            self.assertEqual(read_json(path), {"a": None, "z": 1})
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(SkillStoreError, "invalid_record"):
                read_json(path)

    def test_changed_error_producers_follow_actual_public_boundaries(self):
        manifest = json.loads(
            Path(ROOT, "tests/contracts/registry-error-boundaries.json").read_text()
        )
        raised, listed = set(), set()
        for name in ("paths", "files", "policy"):
            tree = ast.parse(
                Path(ROOT, "src/laomedo/skills/registry", name + ".py").read_text()
            )
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "SkillStoreError"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    raised.add(node.args[0].value)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "errors"
                    and node.func.attr == "append"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    listed.add(node.args[0].value)
        public = set(manifest["runner_error_categories"])
        self.assertEqual(
            raised, public | set(manifest["policy_refusals_collapsed_by_skill_http"])
        )
        self.assertEqual(listed, set(manifest["draft_validation_record_codes"]))
        store = ast.parse(
            Path(ROOT, "src/laomedo/skills/registry/store.py").read_text(
                encoding="utf-8"
            )
        )
        store_codes = {
            node.args[0].value
            for node in ast.walk(store)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"SkillStoreError", "ConflictError"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
        }
        reader_codes = set(manifest["unchanged_store_runner_error_categories"])
        self.assertEqual(
            store_codes,
            reader_codes
            | set(manifest["other_store_codes_requiring_separate_surface_analysis"]),
        )
        public |= reader_codes
        catalogue = json.loads(
            Path(
                ROOT, "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(public - catalogue.keys())
        for code in public:
            self.assertTrue(
                all(
                    catalogue[code][field].strip()
                    for field in ("title", "description", "recovery")
                ),
                code,
            )
        runner = Path(ROOT, "src/laomedo/host/runner/http/handler.py").read_text()
        self.assertIn('"error_category": str(exc)', runner)
        source = Path(
            ROOT, "src/laomedo/skills/interface/operations/handler.py"
        ).read_text()
        self.assertIn('"error_category": "skill_operation_refused"', source)


if __name__ == "__main__":
    unittest.main()
