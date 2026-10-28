"""Internal architecture and record-binding regressions; no real provider acceptance."""
import ast
import inspect
from pathlib import Path
import unittest
from unittest.mock import patch

from laomedo.agents.runtime.runner import Runner
from laomedo.agents.providers.codex.runner import CodexRunner
from laomedo.agents.providers.claude.runner import ClaudeRunner
from laomedo.agents.providers.opencode.runner import OpenCodeRunner
from laomedo.agents.runtime.errors import RunnerError
from laomedo.agents.providers.codex import settings as codex_settings
import test_local_runner
import test_claude_runner
import test_opencode_runner

ROOT = Path(__file__).resolve().parents[1]


class ProviderBoundaryTests(unittest.TestCase):
    def test_shared_runtime_never_imports_concrete_provider_or_credentials(self):
        for path in (ROOT / 'src/laomedo/agents/runtime').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    self.assertFalse(name.startswith(('laomedo.agents.providers.', 'laomedo.host.credentials.')), (path.name, node.lineno, name))
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn(node.value, {'codex', 'claude', 'opencode'}, (path.name, node.lineno))

    def test_providers_extend_only_the_neutral_lifecycle(self):
        for cls in (CodexRunner, ClaudeRunner, OpenCodeRunner):
            self.assertEqual(cls.__bases__, (Runner,))
            self.assertFalse(cls.__abstractmethods__)
        forbidden = {'transport', 'check_docker', 'supervise_containers', 'split_executor',
                     'split_provider_config', 'split_access_token', 'auth_store', 'image_id'}
        self.assertFalse(forbidden & set(inspect.signature(Runner).parameters))
        self.assertFalse(forbidden & set(inspect.signature(OpenCodeRunner).parameters))

    def test_graph_adapters_do_not_inherit_each_other(self):
        for provider in ('codex', 'claude', 'opencode'):
            path = ROOT / f'components/laomedo/{provider}_agent.py'
            tree = ast.parse(path.read_text())
            imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertIn('laomedo.integrations.langflow.agent.component', imports)
            self.assertNotIn('laomedo.codex_agent', imports)
        shared = ROOT / 'src/laomedo/integrations/langflow/agent/component.py'
        for node in ast.walk(ast.parse(shared.read_text())):
            if isinstance(node, ast.Attribute):
                self.assertFalse(isinstance(node.value, ast.Name) and node.value.id == 'self' and node.attr == 'name')

    def fixture(self, cls):
        control = cls()
        control.setUp()
        self.addCleanup(control.doCleanups)
        self.addCleanup(control.tearDown)
        return control

    def assert_record(self, control, request, expected):
        record = control.runner._prepare(request)
        self.assertEqual({key: record[key] for key in expected}, expected)
        self.assertEqual(record, control.runner.status(record['run_id']))
        # Full schema guard: provider-specific additions are intentional, not inherited pins.
        keys = {'schema_version','run_id','status','error_category','source_hash','workspace_mode',
                'git_baseline','post_run_hash_scope','effective_hash','post_run_hash','input_hash',
                'skill','skills','skill_git_exclusion','provider','handoff','imported_artifacts',
                'requested_model','requested_effort','effective_model','effective_effort','profile',
                'execution_mode','image','image_id','cli_version','config_sha256','thread_id',
                'credential','runner_instance_id','turns','answer','output_ref','raw_event_ref',
                'client_request_id','activity_initial_attempt_id','output_requirements',
                'requirements_revision','output_retries','precheck','request_hash','cancel_requested','cancel_confirmed'}
        if control.runner.provider == 'claude':
            keys |= {'runtime_version','turn_timeout','resolved_model','permission_grant','native_tools'}
        self.assertEqual(set(record), keys)
        return record

    def test_codex_prepared_record_preserves_binding(self):
        control = self.fixture(test_local_runner.LocalRunnerTests)
        self.assert_record(control, control.request(), {
            'provider':'codex','profile':codex_settings.VOLUME,'image':codex_settings.IMAGE,
            'image_id':codex_settings.IMAGE_ID,'execution_mode':'legacy',
            'cli_version':codex_settings.CLI_VERSION,'config_sha256':codex_settings.CONFIG_SHA256,
            'credential':None})

    def test_claude_prepared_record_never_contains_codex_binding(self):
        control = self.fixture(test_claude_runner.ClaudeRunnerTests)
        self.assert_record(control, control.payload, {
            'provider':'claude','profile':control.runner.profile,'image':control.runner.image,
            'image_id':control.runner.image_id,'execution_mode':'claude_container',
            'cli_version':'Claude Code ' + test_claude_runner.CLI_VERSION, 'credential':None})

    def test_opencode_prepared_record_never_contains_codex_binding(self):
        control = self.fixture(test_opencode_runner.OpenCodeTests)
        self.assert_record(control, control.payload, {
            'provider':'opencode','profile':None,'image':None,'image_id':None,
            'execution_mode':'opencode_http','cli_version':'opencode 1.18.33',
            'config_sha256':None,'credential':None})

    def test_unsupported_mediation_is_rejected_before_workspace_or_authority(self):
        for cls in (test_claude_runner.ClaudeRunnerTests, test_opencode_runner.OpenCodeTests):
            control = self.fixture(cls)
            with patch.object(control.runner, 'github_authority') as authority:
                with self.assertRaisesRegex(RunnerError, 'mediated_lease_required'):
                    control.runner._prepare({**control.payload, 'github_authorization_ref':'untrusted'})
                authority.bind_run.assert_not_called()
                self.assertEqual(list((control.runner.state/'runs').iterdir()), [])

    def test_claude_and_opencode_do_not_validate_codex_policy(self):
        control = self.fixture(test_local_runner.LocalRunnerTests)
        from types import SimpleNamespace
        with patch.object(codex_settings, 'CONFIG', ROOT/'not-a-codex-policy'):
            claude = ClaudeRunner(control.runner.state.parent/(control.runner.state.name+'-neutral-claude'),
                control.runner.store.root, control.source,
                container=SimpleNamespace(profile='local-unit', image_id='sha256:'+'b'*64))
            opencode = OpenCodeRunner(control.runner.state.parent/(control.runner.state.name+'-neutral-opencode'),
                control.runner.store.root, control.source)
        import shutil
        for runner in (claude, opencode):
            self.addCleanup(shutil.rmtree, runner.state, ignore_errors=True)
