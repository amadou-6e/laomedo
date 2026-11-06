"""Literal public error producers retain descriptive shared entries."""

import ast
import json
import unittest
from support.paths import repository_root


class SkillInspectionErrorCatalogueTests(unittest.TestCase):
    def test_affected_producer_codes_have_descriptive_catalogue_entries(self):
        """Read actual literal producers rather than just a new expected list."""
        root = repository_root()
        catalogue = json.loads(
            (
                root / "frontend/langflow-skill-viewer/errors/node-error-catalog.json"
            ).read_text(encoding="utf-8")
        )
        codes = set()
        for relative in (
            "skills/inspection/utils.py",
            "skills/operations/models.py",
            "skills/authoring/summary.py",
        ):
            tree = ast.parse(
                (root / "src/laomedo" / relative).read_text(encoding="utf-8")
            )
            codes.update(
                node.exc.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and node.exc.args
                and isinstance(node.exc.args[0], ast.Constant)
                and isinstance(node.exc.args[0].value, str)
            )
        self.assertTrue(
            {
                "immutable_skill_revision_required",
                "skill_revision_unavailable",
                "skill_revision_unsafe",
                "skill_revision_too_large",
                "skill_operation_invalid",
                "skill_summary_source_unavailable",
            }
            <= codes
        )
        # Binary edit references can fail inside the private proposal model. The
        # manual HTTP boundary projects this code to skill_manual_invalid.
        self.assertFalse(codes - catalogue.keys() - {"skill_file_missing"})
        for code in codes | {
            "skill_inspection_unavailable",
            "skill_history_unavailable",
            "skill_comparison_unavailable",
        }:
            with self.subTest(code=code):
                entry = catalogue[code]
                self.assertEqual(set(entry), {"title", "description", "recovery"})
                self.assertTrue(
                    all(
                        type(value) is str and value.strip() for value in entry.values()
                    )
                )
                self.assertNotRegex(
                    " ".join(entry.values()).lower(), r"\boperator\b|\brestart\b"
                )
