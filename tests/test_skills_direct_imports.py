"""Direct-symbol Skills ownership controls; internal tests, not live acceptance."""

import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkillsDirectImportTests(unittest.TestCase):

    def test_skills_owned_files_have_no_module_prefix_imports(self):
        for path in (ROOT / "src/laomedo/skills").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        any(item.name.startswith("laomedo.") for item in node.names),
                        (path, node.lineno),
                    )

    def test_affected_error_producers_have_explicit_surface_and_gap_inventory(self):
        """Require descriptive entries for actual current error producers."""
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
        self.assertFalse(codes - catalogue.keys())
        self.assertEqual(inventory["known_missing_entries"], [])
        self.assertEqual(inventory["existing_viewer_catalogue_gaps"], [])
        for code in inventory["catalogued_codes"]:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))
        handler = (
            ROOT / "src/laomedo/skills/interface/operations/handler.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"error_category": "skill_operation_refused"', handler)


if __name__ == "__main__":
    unittest.main()
