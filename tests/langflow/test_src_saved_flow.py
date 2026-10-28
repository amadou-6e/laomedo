"""Migrate an actual archived pre-src graph before loading its component."""
import ast
import importlib.util
import sys
import json
from pathlib import Path
import unittest
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("saved_module_migration", ROOT / "tools/migrations/migrate_module_paths.py")
migration = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(ROOT / 'tools/migrations'))
try:
    _spec.loader.exec_module(migration)
finally:
    sys.path.pop(0)


class SavedFlowMigrationTests(unittest.TestCase):
    def migrated_code(self):
        original = json.loads((ROOT / "tests/fixtures/pre-src-native-flow.json").read_text())
        migrated = migration.migrate_value(original)
        self.assertEqual(migrated["id"], original["id"])
        node = next(n for n in migrated["data"]["nodes"] if n["data"]["type"] == "LaomedoCodexAgent")
        code = node["data"]["node"]["template"]["code"]["value"]
        self.assertIn("from laomedo.agents.contracts.output import", code)
        return code

    def test_archived_component_loads_after_explicit_migration(self):
        code = self.migrated_code()
        template, _ = build_custom_component_template(Component(_code=code))
        self.assertEqual(template["template"]["code"]["value"], code)
        self.assertIn("operation", template["template"])

    def test_migrated_embedded_imports_execute(self):
        imports = [n for n in ast.walk(ast.parse(self.migrated_code()))
                   if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("laomedo.")]
        self.assertTrue(imports)
        for statement in imports:
            with self.subTest(module=statement.module):
                exec(compile(ast.Module(body=[statement], type_ignores=[]), "migrated-import", "exec"), {})
