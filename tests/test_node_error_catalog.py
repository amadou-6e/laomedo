"""Prevent newly emitted Agent codes from silently losing their user explanation."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NodeErrorCatalogueTests(unittest.TestCase):
    def test_literal_agent_failures_have_descriptive_catalogue_entries(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        missing = []
        for source in (ROOT / "components/laomedo").glob("*agent.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                    continue
                argument = node.exc.args[0]
                if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                    continue
                code = argument.value
                if code and all(character.islower() or character.isdigit() or character == "_" for character in code):
                    if code not in catalogue:
                        missing.append(f"{source.name}:{node.lineno}: {code}")
        self.assertEqual(missing, [], "Add a user explanation for each new literal Agent failure code")

    def test_runner_service_public_codes_have_catalogue_coverage(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        source = ast.parse((ROOT / "laomedo/runner_service.py").read_text())
        codes = set()
        for node in ast.walk(source):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in {"reason", "code"}:
                        for literal in ast.walk(value):
                            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                                codes.add(literal.value)
        self.assertTrue(codes)
        self.assertEqual(codes - catalogue.keys(), set())


if __name__ == "__main__":
    unittest.main()
