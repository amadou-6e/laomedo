"""Configuration and exception boundary regression checks; no live acceptance."""
import ast
import importlib
import os
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest.mock import patch

from pydantic_settings import BaseSettings

SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'laomedo'


class SettingsContractTests(unittest.TestCase):
    def classes(self):
        for path in SOURCE.rglob('settings.py'):
            module = importlib.import_module('laomedo.' + '.'.join(path.relative_to(SOURCE).with_suffix('').parts))
            cls = getattr(module, 'Settings', None)
            if cls is not None:
                self.assertTrue(issubclass(cls, BaseSettings))
                yield module, cls

    def test_no_constants_modules_or_retired_imports(self):
        self.assertEqual(list(SOURCE.rglob('constants.py')), [])
        for path in SOURCE.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    self.assertFalse(name.startswith('laomedo.') and '.constants' in name, str(path))

    def test_settings_read_only_explicit_strings_at_point_of_use(self):
        for module, cls in self.classes():
            self.assertTrue(cls.model_config['case_sensitive'])
            self.assertIsNone(cls.model_config['env_file'])
            self.assertIsNone(cls.model_config['secrets_dir'])
            self.assertFalse(cls.model_config['enable_decoding'])
            for name, field in cls.model_fields.items():
                if field.annotation in (int, float):
                    continue  # Numeric host settings have explicit validation below.
                with self.subTest(module=module.__name__, field=name):
                    alias = field.validation_alias
                    with patch.dict(os.environ, {}, clear=True):
                        self.assertEqual(getattr(cls(), name), field.default)
                        for value in ('', '1', 'true', 'yes', ' 1', 'private-test-value'):
                            os.environ[alias] = value
                            settings = cls()  # Import already happened; no stale singleton.
                            self.assertEqual(getattr(settings, name), value)
                            self.assertNotIn('private-test-value', repr(settings))
                            self.assertNotIn('private-test-value', settings.model_dump_json())
                        del os.environ[alias]
                        os.environ[alias.lower()] = 'unexpected'
                        if os.name != 'nt':  # Windows environment keys are case-insensitive.
                            self.assertEqual(getattr(cls(), name), field.default)

    def test_flags_retain_exact_one_comparison_at_consumers(self):
        consumers = {
            'agents/providers/codex/native/server.py': {'otel', 'multi_agent'},
            'agents/providers/claude/runner.py': {'mirror_host_login'},
            'activity/opencode/telemetry.py': {'otel'},
        }
        for relative, fields in consumers.items():
            tree = ast.parse((SOURCE / relative).read_text())
            compared = {node.left.attr for node in ast.walk(tree)
                        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute)
                        and node.left.attr in fields and len(node.comparators) == 1
                        and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == '1'
                        and isinstance(node.ops[0], (ast.Eq, ast.NotEq))}
            self.assertEqual(compared, fields, relative)

    def test_native_stream_settings_validate_positive_numeric_environment(self):
        from pydantic import ValidationError
        from laomedo.agents.providers.codex.native.settings import Settings
        from laomedo.agents.runtime.errors import RunnerError
        for field, alias in (("max_bytes","LAOMEDO_CODEX_STREAM_MAX_BYTES"),
                             ("startup_margin","LAOMEDO_CODEX_STREAM_STARTUP_MARGIN")):
            with self.subTest(field=field), patch.dict(os.environ, {}, clear=True):
                os.environ[alias]="1024"
                self.assertEqual(getattr(Settings(),field),1024)
                for invalid in ("", "0", "-1", "not-a-number"):
                    os.environ[alias]=invalid
                    with self.assertRaises(ValidationError):
                        Settings()
                    with self.assertRaisesRegex(RunnerError,"runner_transport_configuration_invalid"):
                        Settings.load()
        with patch.dict(os.environ,{"LAOMEDO_CODEX_STREAM_STARTUP_MARGIN":"inf"}):
            with self.assertRaisesRegex(RunnerError,"runner_transport_configuration_invalid"):
                Settings.load()

    def test_fixed_protocol_pins_are_not_environment_fields(self):
        for module, cls in self.classes():
            self.assertFalse({name.lower() for name in vars(module) if name.isupper()} & set(cls.model_fields))
            for field in cls.model_fields:
                self.assertFalse(any(part in field for part in ('image', 'sha256', 'timeout', 'label', 'max_body', 'lease_seconds')))

    def test_dotenv_and_secret_directories_are_not_configuration_sources(self):
        from laomedo.skills.sources.settings import Settings
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory)
            (path / '.env').write_text('LAOMEDO_SKILL_SOURCE_URL=http://unexpected\n')
            (path / 'LAOMEDO_SKILL_SOURCE_URL').write_text('http://unexpected')
            self.assertEqual(Settings(_env_file=path / '.env', _secrets_dir=path).url, '')

    def test_missing_viewer_paths_keep_keyerror(self):
        from laomedo.integrations.langflow.settings import Settings
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(KeyError, 'LAOMEDO_SKILL_STORE'):
                Settings().required_path('skill_store')

    def test_raw_environment_boundaries_stay_explicit(self):
        protected = {
            'host/runner/utils.py': 'os.environ.items()',
            'agents/workspace/git.py': 'os.environ.items()',
            'github/transport/git/utils.py': 'os.environ.items()',
            'host/credentials/claude/utils.py': 'os.environ if environment is None',
            'skills/sources/service.py': 'os.environ.items()',
                        'host/publication/cli.py': 'key in os.environ',
            'github/issues/cli.py': 'os.environ.get(args.github_token_env)',
            'github/pull_requests/cli.py': 'os.environ.get(args.github_token_env)',
            'agents/handoffs/transport.py': '"LAOMEDO_" + provider.upper()',
        }
        for relative, expression in protected.items():
            self.assertIn(expression, (SOURCE / relative).read_text(), relative)
        claude=(SOURCE / 'agents/providers/claude/container.py').read_text(encoding='utf-8')
        self.assertNotIn('os.environ', claude)
        self.assertIn('environment={"DOCKER_HOST": self.docker_endpoint}', claude)
        split=(SOURCE / 'agents/providers/codex/split/server.py').read_text()
        self.assertNotIn('os.environ',split)
        self.assertIn('environment=docker_environment',split)
        helper = (SOURCE / 'host/credentials/git_credential_helper.py').read_text()
        self.assertIn('os.environ.get("LAOMEDO_MEDIATED_GIT_TOKEN", "")', helper)
        self.assertNotIn('pydantic', helper)
        self.assertNotIn('import laomedo', helper)


class ErrorContractTests(unittest.TestCase):
    def test_each_domain_exception_has_a_documented_code_contract(self):
        for path in SOURCE.rglob('errors.py'):
            module = importlib.import_module('laomedo.' + '.'.join(path.relative_to(SOURCE).with_suffix('').parts))
            for node in ast.parse(path.read_text()).body:
                if not isinstance(node, ast.ClassDef):
                    continue
                cls = getattr(module, node.name)
                with self.subTest(exception=cls.__name__):
                    self.assertGreater(len(ast.get_docstring(node) or ''), 35)
                    if cls.__name__ == 'RunnerResultError':
                        error = cls({'run_id': 'retained-run', 'error_category': 'runner_transport_failed'})
                        self.assertEqual(error.code, 'runner_transport_failed')
                        self.assertEqual(error.run_reference['run_id'], 'retained-run')
                        continue  # Graph invocation errors retain a record, unlike scalar domain errors.
                    if cls.__name__ == 'PushOutcomeUnknown':
                        error = cls('timeout', None)
                        code = 'push_outcome_unknown'
                    else:
                        code = 'existing_category'
                        error = cls(code)
                    self.assertEqual(error.code, code)
                    self.assertEqual(error.args, (code,))
                    self.assertEqual(str(error), code)
                    restored = pickle.loads(pickle.dumps(error))
                    self.assertEqual(type(restored), cls)
                    self.assertEqual(restored.__dict__, error.__dict__)
                    self.assertEqual(str(restored), code)

    def test_registry_conflict_is_still_a_skill_store_value_error(self):
        from laomedo.skills.registry.errors import ConflictError, SkillStoreError
        error = ConflictError('base_revision_changed')
        self.assertIsInstance(error, SkillStoreError)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.code, 'base_revision_changed')
