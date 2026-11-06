"""Keep the Skill and shared-feedback literal failures descriptively catalogued."""

import ast
import json
import unittest

from support.paths import repository_root


class ErrorCatalogueTests(unittest.TestCase):
    def test_operation_and_handler_codes_have_safe_descriptive_entries(self):
        root = repository_root()
        catalogue = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        codes = {
            "skill_operation_unavailable",
            "skill_operation_service_not_configured",
            "skill_operation_refused",
        }
        for relative in (
            "src/laomedo/skills/interface/operations/handler.py",
            "src/laomedo/skills/interface/sources/handler.py",
        ):
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
            observed = {
                value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Dict)
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant)
                and key.value == "error_category"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            }
            self.assertTrue(observed, relative)
            codes.update(observed)
        self.assertFalse(codes - catalogue.keys())
        for code in codes:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))
        for code in ("skill_operation_unavailable", "skill_operation_refused"):
            self.assertIn("before submitting another", catalogue[code]["recovery"])

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
