"""Structural policy and published migration reachability, not live acceptance."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src' / 'laomedo'


class ModuleCohesionTests(unittest.TestCase):
    def test_files_introduce_classes_or_standalone_functions(self):
        mixed = []
        for path in SOURCE.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            classes = any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
            functions = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)
            if classes and functions:
                mixed.append(path.relative_to(SOURCE).as_posix())
        self.assertEqual(mixed, [], 'Move helpers to methods or the owning feature function modules')

    def test_a_module_never_shadows_a_feature_package(self):
        for path in SOURCE.rglob('*.py'):
            if path.name != '__init__.py':
                self.assertFalse((path.with_suffix('') / '__init__.py').exists(), str(path))

    def test_distinct_feature_imports_never_rebind_the_same_module_alias(self):
        for path in SOURCE.rglob('*.py'):
            aliases = {}
            for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
                if not isinstance(node, ast.Import):
                    continue
                for item in node.names:
                    if item.asname:
                        self.assertFalse(item.asname.startswith('__'), 'Module aliases must not trigger class name mangling: ' + str(path))
                        aliases.setdefault(item.asname, set()).add(item.name)
            self.assertFalse({alias: names for alias, names in aliases.items() if len(names) > 1}, str(path))

    def test_every_published_module_generation_reaches_a_final_owner(self):
        mapping = json.loads((ROOT / 'tools/migrations/module-paths.json').read_text())
        self.assertFalse(set(mapping) & set(mapping.values()), 'Migration must finish in one pass')
        for old, new in mapping.items():
            path = ROOT.joinpath('src', *new.split('.'))
            self.assertTrue(path.with_suffix('.py').is_file() or (path / '__init__.py').is_file(), (old, new))
