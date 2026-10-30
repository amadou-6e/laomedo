"""Resolve every published migration target with the real optional runtime installed."""
import importlib
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MigrationTargetTests(unittest.TestCase):
    def test_migrated_revision_key_matches_the_actual_pinned_lfx_implementation(self):
        from lfx.custom.utils import _generate_code_hash
        sys.path.insert(0, str(ROOT/'tools/migrations'))
        try:
            from migrate_module_paths import migrate_value
            code = 'from laomedo.local_runner import LocalRunner\nlabel = "\u03bb"\n'
            graph = {'nodes': [{'data': {'node': {
                'metadata': {'code_hash': _generate_code_hash(code, 'before')},
                'template': {'code': {'value': code}},
            }}}]}
            definition = migrate_value(graph)['nodes'][0]['data']['node']
            self.assertEqual(definition['metadata']['code_hash'],
                             _generate_code_hash(definition['template']['code']['value'], 'after'))
        finally:
            sys.path.pop(0)

    def test_every_symbol_target_imports_and_exists(self):
        targets = set(json.loads((ROOT / 'tools/migrations/symbol-paths.json').read_text()).values())
        for target in sorted(targets):
            with self.subTest(target=target):
                module, symbol = target.rsplit('.', 1)
                imported = __import__(module, fromlist=[symbol])
                self.assertTrue(hasattr(imported, symbol), target)

    def test_every_cli_target_has_a_callable_main(self):
        targets = set(json.loads((ROOT / 'tools/migrations/cli-paths.json').read_text()).values())
        for target in sorted(targets):
            with self.subTest(target=target):
                self.assertTrue(callable(getattr(importlib.import_module(target), 'main', None)), target)
