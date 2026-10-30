"""Direct-symbol Skills ownership controls; internal tests, not live acceptance."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkillsDirectImportTests(unittest.TestCase):
    @classmethod
    def unqualify(cls, node, aliases):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            return ast.Name(id=node.attr, ctx=node.ctx)
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                setattr(
                    node,
                    field,
                    [
                        (
                            cls.unqualify(item, aliases)
                            if isinstance(item, ast.AST)
                            else item
                        )
                        for item in value
                    ],
                )
            elif isinstance(value, ast.AST):
                setattr(node, field, cls.unqualify(value, aliases))
        return node

    def test_five_function_bodies_preserve_operations_after_direct_imports(self):
        record = json.loads(
            (ROOT / "tests/contracts/skills-direct-imports-b614cf3.json").read_text(
                encoding="utf-8"
            )
        )
        functions = 0
        aliases_seen = 0
        for item in record["files"]:
            old = item["source"]
            self.assertEqual(
                hashlib.sha256(old.encode()).hexdigest(), item["source_sha256"]
            )
            self.assertEqual(
                subprocess.check_output(
                    [
                        "git",
                        "-c",
                        "safe.directory=" + str(ROOT),
                        "show",
                        record["base_revision"] + ":" + item["path"],
                    ],
                    cwd=ROOT,
                ).decode(),
                old,
            )
            old_tree = ast.parse(old)
            aliases = {
                imported.asname
                for node in old_tree.body
                if isinstance(node, ast.Import)
                for imported in node.names
                if imported.name.startswith("laomedo.")
            }
            aliases_seen += len(aliases)
            original = [
                node for node in old_tree.body if isinstance(node, ast.FunctionDef)
            ]
            current = [
                node
                for node in ast.parse(
                    (ROOT / item["path"]).read_text(encoding="utf-8")
                ).body
                if isinstance(node, ast.FunctionDef)
            ]
            self.assertEqual(len(original), len(current))
            for before, after in zip(original, current):
                self.assertEqual(
                    ast.dump(self.unqualify(copy.deepcopy(before), aliases)),
                    ast.dump(after),
                    (item["path"], before.name),
                )
                functions += 1
        self.assertEqual(functions, 5)
        self.assertEqual(aliases_seen, 7)

    def test_skills_owned_files_have_no_module_prefix_imports(self):
        for path in (ROOT / "src/laomedo/skills").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        any(item.name.startswith("laomedo.") for item in node.names),
                        (path, node.lineno),
                    )

    def test_affected_error_producers_have_explicit_surface_and_gap_inventory(self):
        """Guard new gaps without presenting pre-existing raw-code UI as repaired."""
        catalogue = json.loads(
            (ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        producers = (
            "skills/inspection/utils.py",
            "skills/authoring/summary.py",
        )
        codes = set()
        for relative in producers:
            tree = ast.parse(
                (ROOT / "src/laomedo" / relative).read_text(encoding="utf-8")
            )
            codes.update(
                node.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"InspectionError", "SkillStoreError"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            )
        models = ast.parse(
            (ROOT / "src/laomedo/skills/operations/models.py").read_text(
                encoding="utf-8"
            )
        )
        for owner in models.body:
            if isinstance(owner, ast.ClassDef) and owner.name in {
                "FileEdit",
                "SkillProposal",
            }:
                codes.update(
                    node.args[0].value
                    for node in ast.walk(owner)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "SkillStoreError"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                )
        self.assertTrue(codes)
        inventory = json.loads(
            (ROOT / "tests/contracts/skills-direct-import-errors.json").read_text(
                encoding="utf-8"
            )
        )
        classified = (
            set(inventory["catalogued_codes"])
            | set(inventory["existing_viewer_catalogue_gaps"])
            | set(inventory["operation_http_collapsed_codes"])
        )
        self.assertEqual(codes, classified)
        self.assertFalse(
            codes - catalogue.keys() - set(inventory["known_missing_entries"])
        )
        for code in inventory["catalogued_codes"]:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))
        handler = (
            ROOT / "src/laomedo/skills/interface/operations/handler.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"error_category": "skill_operation_refused"', handler)


if __name__ == "__main__":
    unittest.main()
