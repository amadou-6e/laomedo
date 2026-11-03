"""Source repository and HTTP failures must remain descriptively catalogued."""

import ast
import json
import unittest

from support.paths import repository_root


class SourceErrorCatalogueTests(unittest.TestCase):
    def test_repository_and_http_client_public_codes_have_recovery_entries(self):
        root = repository_root()
        catalog = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        for relative in (
            "src/laomedo/skills/sources/repository.py",
            "src/laomedo/skills/interface/sources/client.py",
        ):
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
            codes = set()
            dynamic = []
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Raise)
                    and isinstance(node.exc, ast.Call)
                    and node.exc.args
                ):
                    argument = node.exc.args[0]
                    if isinstance(argument, ast.Constant) and isinstance(
                        argument.value, str
                    ):
                        codes.add(argument.value)
                    elif not (
                        isinstance(argument, ast.Name) and argument.id == "category"
                    ):
                        dynamic.append(node.lineno)
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "category"
                    for target in node.targets
                ):
                    self.assertIsInstance(node.value, ast.Constant, relative)
                    self.assertIsInstance(node.value.value, str, relative)
                    codes.add(node.value.value)
            with self.subTest(producer=relative):
                self.assertTrue(codes, "Scan the actual non-empty affected producer")
                self.assertEqual(
                    dynamic,
                    [],
                    "An unclassified dynamic public code needs explicit coverage",
                )
                self.assertIn("repository_cleanup_unverified", codes)
                self.assertFalse(codes - catalog.keys(), codes - catalog.keys())
                for code in codes:
                    with self.subTest(code=code):
                        for field in ("title", "description", "recovery"):
                            self.assertIsInstance(catalog[code][field], str)
                            self.assertTrue(catalog[code][field].strip())
