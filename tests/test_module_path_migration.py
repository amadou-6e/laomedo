"""Offline migration preserves behavior, identities and original files."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools/migrations/migrate_module_paths.py"
sys.path.insert(0, str(TOOL.parent))
_spec = importlib.util.spec_from_file_location("module_path_migration_test", TOOL)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


class ModuleMigrationTests(unittest.TestCase):
    def test_embedded_provider_nodes_migrate_to_neutral_base_without_overwriting_custom_methods(self):
        for provider in ('Claude', 'OpenCode'):
            source = ('from laomedo.codex_agent import LaomedoCodexAgent as Component\n'
                      f'class Laomedo{provider}Agent(Component):\n'
                      '    name = "custom-visible-name"\n'
                      '    def custom_method(self):\n        return "preserve-me"\n')
            result = migration.migrate_source(source)
            self.assertIn('AgentComponent as Component', result)
            self.assertNotIn('laomedo.codex_agent', result)
            self.assertIn('return "preserve-me"', result)
            self.assertIn('supports_output_requirements = ' + str(provider == 'Claude'), result)
            self.assertEqual(migration.migrate_source(result), result)
        source = 'from laomedo.codex_agent import LaomedoCodexAgent\nnode = LaomedoCodexAgent()'
        self.assertEqual(migration.migrate_source(source), source)

    def test_legacy_agent_migration_retains_class_docstring_and_line_endings(self):
        source = ('from laomedo.codex_agent import LaomedoCodexAgent as Component\r\n'
                  'class LaomedoClaudeAgent(Component):\r\n'
                  '    """Keep this class documentation."""\r\n'
                  '    name = "custom"\r\n')
        result = migration.migrate_source(source)
        self.assertNotIn('\n', result.replace('\r\n', ''))
        tree = ast.parse(result)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        self.assertEqual(ast.get_docstring(cls), 'Keep this class documentation.')
        self.assertEqual(migration.migrate_source(result), result)

    def test_intermediate_runtime_symbols_reach_final_owner(self):
        source = 'from laomedo.agents.runtime.runner import LocalRunner\n'
        result = migration.migrate_source(source)
        self.assertIn('agents.codex.agent import CodexAgent as LocalRunner', result)
        self.assertEqual(migration.migrate_source(result), result)
        source = 'import laomedo.agents.runtime.runner as runtime\nrunner = runtime.LocalRunner\n'
        result = migration.migrate_source(source)
        namespace = {}
        exec(result, namespace)
        self.assertEqual(namespace['runner'].__module__, 'laomedo.agents.agents.codex.agent')

    def test_constants_generation_migrates_symbols_and_aliases_in_one_pass(self):
        renamed = {old: new for old, new in migration.MODULE_PATHS.items()
                   if old.endswith('.constants')}
        # The retired OpenCode SSE settings generation has no current owner.
        self.assertEqual(len(renamed), 21)
        for old, new in renamed.items():
            symbols = {key.rsplit('.', 1)[1]: value
                       for key, value in migration.SYMBOL_PATHS.items()
                       if key.rsplit('.', 1)[0] == old}
            definitions = set()
            for owner in {target.rsplit('.', 1)[0] for target in symbols.values()}:
                path = TOOL.parents[2].joinpath('src', *owner.split('.')).with_suffix('.py')
                for node in ast.parse(path.read_text()).body:
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        for assigned in node.targets if isinstance(node, ast.Assign) else [node.target]:
                            definitions.update(item.id for item in ast.walk(assigned) if isinstance(item, ast.Name))
            self.assertLessEqual(set(symbols), definitions, old)  # New constants were never part of the retired generation.
            for name, target in symbols.items():
                for source in (f'from {old} import {name}\nvalue = {name}\n',
                               f'import {old} as settings\nvalue = settings.{name}\n'):
                    with self.subTest(module=old, name=name, source=source):
                        result = migration.migrate_source(source)
                        self.assertIn(target.rsplit('.', 1)[0], result)
                        self.assertNotIn(old, result)
                        self.assertEqual(migration.migrate_source(result), result)

    def test_all_current_module_imports_are_current_even_under_reused_packages(self):
        for path in (TOOL.parents[2] / 'src/laomedo').rglob('*.py'):
            if path.name == '__init__.py':
                continue
            module = '.'.join(path.relative_to(TOOL.parents[2] / 'src').with_suffix('').parts)
            source = f'import {module}\n'
            with self.subTest(module=module):
                self.assertEqual(migration.migrate_source(source), source)

    def test_reused_package_names_accept_flat_intermediate_and_current_inputs(self):
        cases = [
            ('laomedo.handoffs', 'BoundedController', 'laomedo.agents.orchestration.controller'),
            ('laomedo.agents.handoffs', 'BoundedController', 'laomedo.agents.orchestration.controller'),
            ('laomedo.artifacts', 'ArtifactError', 'laomedo.agents.artifacts.errors'),
            ('laomedo.agents.artifacts', 'ArtifactError', 'laomedo.agents.artifacts.errors'),
        ]
        for old, symbol, current in cases:
            with self.subTest(old=old):
                result = migration.migrate_source(f'from {old} import {symbol}\n')
                self.assertIn(current, result)
                self.assertEqual(migration.migrate_source(result), result)
                canonical_symbol = "AgentHandoffController" if symbol == "BoundedController" else symbol
                canonical = f'import {current}\nvalue = {current}.{canonical_symbol}\n'
                self.assertEqual(migration.migrate_source(canonical), canonical)
        path = TOOL.parents[2] / 'examples/agent-handoffs/loop-flow.json'
        result = subprocess.run([sys.executable, str(TOOL), str(path), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsafe_dotted_and_keyword_forms_require_manual_migration(self):
        sources = [
            'patch("laomedo.local_runner.subprocess.run")',
            'import laomedo.local_runner\nx = laomedo.local_runner.RunnerError',
            'from laomedo.container_lease import cleanup_exact\ncleanup_exact("n", "r", token=t)',
            'from laomedo.container_lease import cleanup_exact\ncleanup_exact(name="n", run_id="r", token=t)',
            'from laomedo.agent_activity import ActivityStore\nstore.start(owner, flow, node=n)',
            'import laomedo.work_graph.model as models\nmodels.WorkItem("a")',
            'from laomedo.agent_activity import capture_for\nr = capture_for(c)\ns, i = r',
        ]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(migration.ManualMigrationRequired):
                migration.migrate_source(source)

    def test_check_refuses_unmapped_dotted_patch_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.py'
            source = 'patch("laomedo.local_runner.subprocess.run")'
            path.write_text(source)
            result = subprocess.run([sys.executable, str(TOOL), str(path), '--check'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('manual', result.stdout.lower() + result.stderr.lower())
            self.assertEqual(path.read_text(), source)

    def test_removed_procedural_git_apis_require_explicit_object_migration(self):
        sources = [
            'from laomedo.git_workspace import prepare_git_workspace\n',
            'from laomedo.agents.workspaces.git import _bounded_git\n',
            'from laomedo.github.transport.git.utils import _credential_environment\n',
            'import laomedo.github_git_transport as git\ngit._run_bounded_tree(args)\n',
        ]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(migration.ManualMigrationRequired):
                migration.migrate_source(source)

    def test_renamed_server_symbol_in_its_final_module_is_migrated(self):
        source = "import laomedo.skill_operation_server as api\nvalue = api.server(ops, token)\n"
        result = migration.migrate_source(source)
        self.assertIn('SkillOperationServer', result)
        self.assertNotIn('api.server(', result)
        with self.assertRaises(migration.ManualMigrationRequired):
            migration.migrate_source('from laomedo.lease_service import _handler\nvalue = _handler(book)\n')

    def test_all_published_generations_reach_defining_symbols_in_one_pass(self):
        for module in ('laomedo.local_runner', 'laomedo.agents.local_runner'):
            with self.subTest(module=module):
                source = f'from {module} import LocalRunner, RunnerError, _hash_tree\n'
                migrated = migration.migrate_source(source)
                self.assertEqual(migration.migrate_source(migrated), migrated)
                namespace = {}
                exec(migrated, namespace)
                self.assertEqual(namespace['LocalRunner'].__module__, 'laomedo.agents.agents.codex.agent')
                self.assertEqual(namespace['RunnerError'].__module__, 'laomedo.agents.errors')
                self.assertEqual(namespace['_hash_tree'].__module__, 'laomedo.agents.workspaces.utils')

    def test_moved_module_attributes_keep_aliases(self):
        source = 'import laomedo.agents.local_runner as runner\nerror = runner.RunnerError\n'
        namespace = {}
        exec(migration.migrate_source(source), namespace)
        self.assertEqual(namespace['error'].__module__, 'laomedo.agents.errors')

    def test_physical_line_offsets_ignore_unicode_text_separators(self):
        source = '"""First\u2028second\fthird"""\nimport laomedo.local_runner as runner\nerror = runner.RunnerError\n'
        namespace = {}
        exec(migration.migrate_source(source), namespace)
        self.assertEqual(namespace['error'].__module__, 'laomedo.agents.errors')
        source = 'from laomedo.local_runner import LocalRunner\r'
        self.assertEqual(migration.migrate_source(source), 'from laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner\r')

    def test_changed_typed_interfaces_require_explicit_manual_migration(self):
        sources = [
            'from laomedo.container_lease import cleanup_exact\ncleanup_exact("n", "r", "t")',
            'from laomedo.agent_activity import capture_for\nstore, invocation = capture_for(component)',
            'from laomedo.agent_activity import ActivityStore\nstore.start("owner", "flow", "node")',
            'from laomedo.local_runner import unknown_retired_symbol',
            'import laomedo.local_runner as runner\ngetattr(runner, "RunnerError")',
            'from laomedo.work_graph.model import GraphSnapshot\nfrom dataclasses import asdict\nasdict(snapshot)',
            'from laomedo.work_graph.model import Dependency\nDependency("a", "b")',
        ]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(migration.ManualMigrationRequired):
                migration.migrate_source(source)

    def test_cli_and_object_imports_use_distinct_final_modules(self):
        self.assertIn('agents.codex.agent', migration.migrate_source('from laomedo.local_runner import LocalRunner'))
        self.assertEqual(migration.migrate_source('python -m laomedo.local_runner'), 'python -m laomedo.agents.agents.codex.cli')
        self.assertEqual(migration.migrate_value({'module': 'laomedo.local_runner'}), {'module': 'laomedo.agents.agents.codex.cli'})

    def test_inline_import_with_unicode_keeps_statement_structure(self):
        source = "label = 'ÃƒÅ½Ã‚Â»'; from laomedo import local_runner, skill_store\n"
        namespace = {}
        exec(migration.migrate_source(source), namespace)
        self.assertEqual(namespace["label"], "ÃƒÅ½Ã‚Â»")
        self.assertTrue(hasattr(namespace["local_runner"], "CodexAgent"))
        self.assertTrue(hasattr(namespace["skill_store"], "SkillStore"))

    def test_aliases_and_multiline_imports_keep_local_names(self):
        source = "from laomedo import (agent_activity, local_runner as runner)\n"
        rewritten = migration.migrate_source(source)
        self.assertIn("from laomedo.agents.activity import store as agent_activity", rewritten)
        self.assertIn("from laomedo.agents.agents.codex import agent as runner", rewritten)
        namespace = {}
        exec(rewritten, namespace)
        self.assertTrue(hasattr(namespace["agent_activity"], "ActivityStore"))
        self.assertTrue(hasattr(namespace["runner"], "CodexAgent"))

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
            self.assertIn("laomedo.agents.agents.codex.agent", path.read_text())
            changed = json.dumps({"code": "import laomedo.skill_store"}).encode()
            path.write_bytes(changed)
            refused = subprocess.run([sys.executable, str(TOOL), str(path), "--apply"], capture_output=True, timeout=30)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(path.read_bytes(), changed)
            self.assertEqual(path.with_name(path.name + ".before-module-migration").read_bytes(), original)
