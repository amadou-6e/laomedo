"""Load an actual pre-src export without updating its embedded component code."""
import ast
import json
from pathlib import Path
import unittest

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template

ROOT = Path(__file__).resolve().parents[2]


class SavedFlowCompatibilityTests(unittest.TestCase):
    def test_pre_refactor_embedded_component_loads_unchanged(self):
        flow = json.loads((ROOT / "tests/fixtures/pre-src-native-flow.json").read_text())
        node = next(n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoCodexAgent")
        code = node["data"]["node"]["template"]["code"]["value"]
        self.assertIn("from laomedo.output_contract import", code)
        self.assertNotIn("from laomedo.agents.output_contract import", code)
        template, _ = build_custom_component_template(Component(_code=code))
        self.assertEqual(template["template"]["code"]["value"], code)
        self.assertIn("operation", template["template"])

    def test_embedded_legacy_imports_execute(self):
        flow = json.loads((ROOT / "tests/fixtures/pre-src-native-flow.json").read_text())
        node = next(n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoCodexAgent")
        code = node["data"]["node"]["template"]["code"]["value"]
        imports = [n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.ImportFrom)
                   and (n.module or "").startswith("laomedo.")]
        self.assertTrue(imports)
        for statement in imports:
            with self.subTest(module=statement.module):
                exec(compile(ast.Module(body=[statement], type_ignores=[]), "pre-src-import", "exec"), {})
