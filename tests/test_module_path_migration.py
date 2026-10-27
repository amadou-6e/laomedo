"""Offline migration preserves behavior, identities and original files."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools/migrations/migrate_module_paths.py"
_spec = importlib.util.spec_from_file_location("module_path_migration_test", TOOL)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


class ModuleMigrationTests(unittest.TestCase):
    def test_inline_import_with_unicode_keeps_statement_structure(self):
        source = "label = 'λ'; from laomedo import local_runner, skill_store\n"
        namespace = {}
        exec(migration.migrate_source(source), namespace)
        self.assertEqual(namespace["label"], "λ")
        self.assertTrue(hasattr(namespace["local_runner"], "LocalRunner"))
        self.assertTrue(hasattr(namespace["skill_store"], "SkillStore"))

    def test_aliases_and_multiline_imports_keep_local_names(self):
        source = "from laomedo import (agent_activity, local_runner as runner)\n"
        rewritten = migration.migrate_source(source)
        self.assertIn("from laomedo.activity.agent_activity import store as agent_activity", rewritten)
        self.assertIn("from laomedo.agents import local_runner as runner", rewritten)
        namespace = {}
        exec(rewritten, namespace)
        self.assertTrue(hasattr(namespace["agent_activity"], "ActivityStore"))
        self.assertTrue(hasattr(namespace["runner"], "LocalRunner"))

    def test_graph_migration_is_idempotent_and_preserves_identity(self):
        value = {"id": "laomedo.local_runner", "run_id": "existing-run", "task": "Explain laomedo.local_runner", "code": "from laomedo.skill_store import SkillStore\n"}
        rewritten = migration.migrate_value(value)
        self.assertEqual(rewritten["id"], value["id"])
        self.assertEqual(rewritten["run_id"], value["run_id"])
        self.assertEqual(rewritten["task"], value["task"])
        self.assertEqual(migration.migrate_value(rewritten), rewritten)
        self.assertEqual(value["code"], "from laomedo.skill_store import SkillStore\n")

    def test_apply_keeps_backup_and_preview_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flow.json"
            original = json.dumps({"code": "import laomedo.local_runner"}).encode()
            path.write_bytes(original)
            preview = subprocess.run([sys.executable, str(TOOL), str(path)], capture_output=True, timeout=30)
            self.assertEqual(preview.returncode, 0)
            self.assertEqual(path.read_bytes(), original)
            applied = subprocess.run([sys.executable, str(TOOL), str(path), "--apply"], capture_output=True, timeout=30)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(path.with_name(path.name + ".before-module-migration").read_bytes(), original)
            self.assertIn("laomedo.agents.local_runner", path.read_text())
            changed = json.dumps({"code": "import laomedo.skill_store"}).encode()
            path.write_bytes(changed)
            refused = subprocess.run([sys.executable, str(TOOL), str(path), "--apply"], capture_output=True, timeout=30)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(path.read_bytes(), changed)
            self.assertEqual(path.with_name(path.name + ".before-module-migration").read_bytes(), original)
