"""Keep the Skill and shared-feedback literal failures descriptively catalogued."""

import ast
import json
import unittest

from support.paths import repository_root


class ErrorCatalogueTests(unittest.TestCase):
    def test_removed_request_recovery_names_the_available_controls(self):
        root = repository_root()
        catalog = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        recovery = catalog["skill_feedback_request_required"]["recovery"]
        self.assertNotIn("Edit Request", recovery)
        for control in ("Operation", "Skill files", "Publish"):
            self.assertIn(control, recovery)
        self.assertIn(
            "Advanced settings",
            catalog["immutable_skill_revision_required"]["recovery"],
        )

    def test_skill_and_feedback_producers_have_descriptive_entries(self):
        root = repository_root()
        catalog = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        for relative in (
            "components/laomedo/skill.py",
            "src/laomedo/agents/feedback/pr.py",
        ):
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
            codes = {
                node.exc.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and node.exc.args
                and isinstance(node.exc.args[0], ast.Constant)
                and isinstance(node.exc.args[0].value, str)
            }
            with self.subTest(producer=relative):
                self.assertTrue(codes, "The affected producer must still be scanned")
                self.assertFalse(codes - catalog.keys())
            for code in codes:
                with self.subTest(producer=relative, code=code):
                    for field in ("title", "description", "recovery"):
                        self.assertIsInstance(catalog[code][field], str)
                        self.assertTrue(catalog[code][field].strip())

    def test_viewer_read_failures_have_specific_catalogue_entries(self):
        root = repository_root()
        catalog = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        codes = {
            "skill_inspection_unavailable",
            "skill_history_unavailable",
            "skill_comparison_unavailable",
            "skill_revision_unavailable",
            "skill_revision_unsafe",
            "skill_revision_too_large",
        }
        self.assertFalse(codes - catalog.keys())
        for code in codes:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalog[code][field].strip(), (code, field))
