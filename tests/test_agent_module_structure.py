"""Keep the agreed discoverable Agent ownership from silently regressing."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src/laomedo'


class AgentModuleStructureTests(unittest.TestCase):
    def module_imports(self, path, tree):
        """Find both ordinary and from-import module bindings in owned source."""
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(i.name for i in node.names if i.name.startswith('laomedo.'))
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = path.parent
                    for _ in range(node.level - 1):
                        parent = parent.parent
                    base = parent.joinpath(*(node.module or '').split('.')) if node.module else parent
                elif (node.module or '').startswith('laomedo.'):
                    base = ROOT.parent.joinpath(*node.module.split('.'))
                else:
                    continue
                for item in node.names:
                    candidate = base / item.name
                    if candidate.with_suffix('.py').is_file() or (candidate/'__init__.py').is_file():
                        found.append(str(candidate))
        return found

    def test_module_binding_guard_detects_from_aliases_and_relative_modules(self):
        path = ROOT/'agents/agents/codex/agent.py'
        for source in ('import laomedo.agents.errors as e',
                       'from laomedo.agents import errors as e',
                       'from . import settings as config'):
            self.assertTrue(self.module_imports(path, ast.parse(source)), source)
        self.assertFalse(self.module_imports(path, ast.parse('from laomedo.agents.errors import RunnerError')))

    def test_owned_agent_files_use_direct_symbols_and_module_level_classes(self):
        for path in (ROOT/'agents').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            top_classes = {id(n) for n in tree.body if isinstance(n, ast.ClassDef)}
            self.assertEqual(self.module_imports(path, tree), [], path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.assertIn(id(node), top_classes, (path, node.lineno))
                if isinstance(node, ast.Import):
                    self.assertFalse(any(i.name.startswith('laomedo.') for i in node.names), (path, node.lineno))

    def test_public_contracts_and_base_do_not_import_concrete_agents(self):
        for folder in ('agents/interface', 'agents/agents/base'):
            for path in (ROOT/folder).rglob('*.py'):
                for node in ast.walk(ast.parse(path.read_text())):
                    if not isinstance(node, ast.ImportFrom):
                        continue
                    module = node.module or ''
                    self.assertFalse(any(module.startswith('laomedo.agents.agents.'+provider) for provider in ('codex', 'claude', 'opencode')), (path, node.lineno))
                    if folder == 'agents/interface':
                        self.assertFalse(module.startswith('laomedo.agents.agents.base'), (path, node.lineno))

    def test_class_owning_agent_leaves_have_an_interface_readme(self):
        for path in (ROOT/'agents').rglob('*.py'):
            tree = ast.parse(path.read_text())
            if any(isinstance(node, ast.ClassDef) for node in tree.body):
                self.assertTrue(path.with_name('README.md').is_file(), path)

    def test_retired_provider_and_graph_owners_do_not_return(self):
        for relative in ('agents/providers', 'agents/runtime', 'agents/protocol', 'agents/contracts',
                         'agents/workflow', 'agents/feedback', 'agents/handoffs', 'activity'):
            self.assertEqual(list((ROOT/relative).rglob('*.py')), [], relative)
        for provider in ('codex', 'claude', 'opencode'):
            self.assertTrue((ROOT/'agents/agents'/provider/'agent.py').is_file())
            self.assertTrue((ROOT/'agents/agents'/provider/'README.md').is_file())


if __name__ == '__main__':
    unittest.main()
