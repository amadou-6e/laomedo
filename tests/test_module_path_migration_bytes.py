"""Protect user-file bytes and safe failure behavior during offline migration."""
from pathlib import Path
from hashlib import sha256
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_module_path_migration import TOOL; from test_module_path_migration import migration


class MigrationFileTests(unittest.TestCase):
    def test_changed_code_with_a_stale_twelve_digit_revision_requires_manual_work(self):
        graph = {'nodes': [{'data': {'node': {'metadata': {'code_hash': '0123456789ab'},
                 'template': {'code': {'value': 'import laomedo.local_runner\n'}}}}}]}
        source = json.dumps(graph)
        with self.assertRaisesRegex(migration.ManualMigrationRequired, 'does not match its original source'):
            migration.migrate_json_source(source)
        self.assertEqual(json.dumps(graph), source)

    def test_unchanged_code_keeps_a_stale_or_external_revision_key_byte_exact(self):
        graph = {'nodes': [{'data': {'node': {'metadata': {'code_hash': '0123456789ab'},
                 'template': {'code': {'value': 'answer = "\u03bb"\n'}}}}}]}
        source = json.dumps(graph, indent=2, ensure_ascii=False)
        self.assertEqual(migration.migrate_json_source(source), source)
        self.assertEqual(migration.migrate_value(graph), graph)

    def test_component_revision_hash_follows_code_without_changing_graph_identity(self):
        """Refresh the actual cache key along with imports, preserving saved user data."""
        code = 'from laomedo.local_runner import LocalRunner\n'
        original_hash = sha256(code.encode()).hexdigest()[:12]
        graph = {'id': 'saved-flow', 'data': {'nodes': [{'id': 'agent', 'data': {'node': {
            'metadata': {'code_hash': original_hash, 'custom': 'keep'},
            'template': {'code': {'value': code}, 'task': {'value': 'laomedo.local_runner'},
                         'run_reference_json': {'value': 'existing-run-reference'}},
        }}}], 'edges': []}}
        source = json.dumps(graph, indent=2)
        result = migration.migrate_json_source(source)
        updated = json.loads(result)
        definition = updated['data']['nodes'][0]['data']['node']
        migrated = definition['template']['code']['value']
        self.assertEqual(definition['metadata']['code_hash'], sha256(migrated.encode()).hexdigest()[:12])
        self.assertEqual(result, source.replace(json.dumps(code), json.dumps(migrated)).replace(original_hash, definition['metadata']['code_hash']))
        self.assertEqual(migration.migrate_value(graph), updated)
        self.assertEqual(migration.migrate_json_source(result), result)

    def test_unknown_revision_format_requires_manual_migration(self):
        """Do not assume an unknown component revision scheme is a source checksum."""
        graph = {'nodes': [{'data': {'node': {'metadata': {'code_hash': 'other-format'},
                 'template': {'code': {'value': 'import laomedo.local_runner\n'}}}}}]}
        with self.assertRaisesRegex(migration.ManualMigrationRequired, 'Unknown component code hash format'):
            migration.migrate_json_source(json.dumps(graph))

    def test_json_splicing_preserves_unrelated_bytes(self):
        source = '\ufeff{\r\n "id":"laomedo.local_runner", "label":"Caf\u00e9 \u03bb", "number":1.2300e+03, "dup":1,"dup":2, "code":"from laomedo.skill_store import SkillStore\\n"\r\n}\r\n'.encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'graph.json'; path.write_bytes(source)
            result = subprocess.run([sys.executable, str(TOOL), str(path), '--apply'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_bytes(), source.replace(b'from laomedo.skill_store import', b'from laomedo.skills.registry.store import'))
            self.assertEqual(path.with_name(path.name + '.before-module-migration').read_bytes(), source)

    def test_python_bom_and_lf_are_preserved(self):
        source = b'\xef\xbb\xbffrom laomedo.local_runner import LocalRunner\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'launch.py'; path.write_bytes(source)
            result = subprocess.run([sys.executable, str(TOOL), str(path), '--apply'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_bytes(), b'\xef\xbb\xbffrom laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner\n')

    def test_unparseable_import_requires_manual_migration(self):
        source = 'from laomedo import local_runner\nif (\n'
        with self.assertRaises(migration.ManualMigrationRequired):migration.migrate_source(source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.py'; path.write_text(source)
            before = path.read_bytes()
            result = subprocess.run([sys.executable, str(TOOL), str(path), '--check'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b'manual migration', result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_only_code_and_explicit_launcher_fields_are_selected(self):
        old = 'laomedo.local_runner'
        graph = {'nodes': [{'data': {'module': old, 'args': [old], 'node': {'template': {
            'code': {'value': 'import ' + old}, 'task': {'value': old}}}}}]}
        migrated = migration.migrate_value(graph); data = migrated['nodes'][0]['data']
        self.assertEqual(data['module'], old); self.assertEqual(data['args'], [old])
        self.assertEqual(data['node']['template']['task']['value'], old)
        self.assertEqual(data['node']['template']['code']['value'], 'import laomedo.agents.agents.codex.agent')
        launcher = {'command': 'python -m ' + old, 'nested': {'command': old}}
        self.assertEqual(migration.migrate_value(launcher), {'command': 'python -m laomedo.agents.agents.codex.cli', 'nested': {'command': old}})

    def test_removed_intermediate_import_is_migrated(self):
        source = 'from laomedo.activity import agent_activity_capture as capture\n'
        migrated = migration.migrate_source(source)
        self.assertEqual(migrated, 'from laomedo.agents.activity import capture\n')
        namespace = {}; exec(migrated, namespace)
        self.assertTrue(hasattr(namespace['capture'], 'ActivityCapture'))

    def test_check_mode_reports_changes_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'launch.py'; path.write_bytes(b'import laomedo.local_runner\n')
            original = path.read_bytes()
            result = subprocess.run([sys.executable, str(TOOL), str(path), '--check'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 1); self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name(path.name + '.before-module-migration').exists())

    def test_batch_preflight_prevents_partial_apply_on_backup_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / 'first.py'; second = Path(directory) / 'second.py'
            first.write_bytes(b'import laomedo.local_runner\n'); second.write_bytes(b'import laomedo.skill_store\n')
            backup = second.with_name(second.name + '.before-module-migration'); backup.write_bytes(b'earlier backup')
            result = subprocess.run([sys.executable, str(TOOL), str(first), str(second), '--apply'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2); self.assertEqual(first.read_bytes(), b'import laomedo.local_runner\n')
            self.assertFalse(first.with_name(first.name + '.before-module-migration').exists())
            self.assertEqual(backup.read_bytes(), b'earlier backup')

    def test_atomic_replace_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'launch.py'; path.write_bytes(b'original')
            with patch.object(migration.os, 'replace', side_effect=OSError('test interrupted replace')):
                with self.assertRaises(OSError):migration._atomic_write(path, b'updated')
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ['launch.py'])
