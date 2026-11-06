"""Classify registry producers and enforce catalogue coverage at public readers."""

import ast
import json
from pathlib import Path
import unittest
from support.paths import repository_root


class RegistryErrorContractTests(unittest.TestCase):
    def test_error_producers_remain_classified_and_public_codes_are_catalogued(self):
        root = repository_root()
        contract = json.loads(
            (Path(__file__).parent / "data/error-boundaries.json").read_text(
                encoding="utf-8"
            )
        )
        raised, validation = set(), set()
        for name in ("paths", "files", "policy", "store"):
            tree = ast.parse(
                (root / "src/laomedo/skills/registry" / (name + ".py")).read_text(
                    encoding="utf-8"
                )
            )
            observed = {
                node.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"SkillStoreError", "ConflictError"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            }
            self.assertTrue(observed, name)
            raised.update(observed)
            validation.update(
                node.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "errors"
                and node.func.attr == "append"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            )
        public = set(contract["public_runner_codes"])
        self.assertEqual(
            raised,
            public
            | set(contract["policy_refusals"])
            | set(contract["other_store_codes"]),
        )
        self.assertEqual(
            validation,
            set(contract["draft_validation_codes"])
            | set(contract["store_review_validation_codes"]),
        )
        catalogue = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(public - catalogue.keys())
        for code in public:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))
