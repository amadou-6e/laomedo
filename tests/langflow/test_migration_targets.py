"""Resolve every published migration target with the real optional runtime installed."""
import importlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MigrationTargetTests(unittest.TestCase):
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
