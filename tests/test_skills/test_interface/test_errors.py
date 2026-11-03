"""Keep the Skill and shared-feedback literal failures descriptively catalogued."""

import ast
import json
import unittest

from support.paths import repository_root


class ErrorCatalogueTests(unittest.TestCase):
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
