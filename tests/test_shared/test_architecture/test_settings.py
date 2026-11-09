"""Configuration and exception boundary regression checks; no live acceptance."""

from support.paths import repository_root

import ast
import importlib
import os
from pathlib import Path
import pickle
from subprocess import TimeoutExpired
import tempfile
import unittest
from unittest.mock import patch

from pydantic_settings import BaseSettings

SOURCE = repository_root() / "src" / "laomedo"


class SettingsContractTests(unittest.TestCase):
    def classes(self):
        for path in SOURCE.rglob("settings.py"):
            module = importlib.import_module(
                "laomedo." + ".".join(path.relative_to(SOURCE).with_suffix("").parts)
            )
            cls = getattr(module, "Settings", None)
            if cls is not None:
                self.assertTrue(issubclass(cls, BaseSettings))
                yield module, cls

    def test_no_constants_modules_or_retired_imports(self):
        self.assertEqual(list(SOURCE.rglob("constants.py")), [])
        for path in SOURCE.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                names = (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                )
                for name in names:
                    self.assertFalse(
                        name.startswith("laomedo.") and ".constants" in name, str(path)
                    )

    def test_settings_read_only_explicit_strings_at_point_of_use(self):
        for module, cls in self.classes():
            self.assertTrue(cls.model_config["case_sensitive"])
            self.assertIsNone(cls.model_config["env_file"])
            self.assertIsNone(cls.model_config["secrets_dir"])
            self.assertFalse(cls.model_config["enable_decoding"])
            for name, field in cls.model_fields.items():
                if field.annotation in {int, float}:
                    continue  # Positive transport budgets have their own typed checks.
                self.assertIn(field.annotation, (str, str | None))
                with self.subTest(module=module.__name__, field=name):
                    alias = field.validation_alias
                    with patch.dict(os.environ, {}, clear=True):
                        self.assertEqual(getattr(cls(), name), field.default)
                        for value in (
                            "",
                            "1",
                            "true",
                            "yes",
                            " 1",
                            "private-test-value",
                        ):
                            os.environ[alias] = value
                            settings = (
                                cls()
                            )  # Import already happened; no stale singleton.
                            self.assertEqual(getattr(settings, name), value)
                            self.assertNotIn("private-test-value", repr(settings))
                            self.assertNotIn(
                                "private-test-value", settings.model_dump_json()
                            )
                        del os.environ[alias]
                        os.environ[alias.lower()] = "unexpected"
                        if (
                            os.name != "nt"
                        ):  # Windows environment keys are case-insensitive.
                            self.assertEqual(getattr(cls(), name), field.default)

    def test_numeric_transport_budgets_validate_at_point_of_use(self):
        from pydantic import ValidationError

        checked = set()
        for module, cls in self.classes():
            for name, field in cls.model_fields.items():
                if field.annotation not in {int, float}:
                    continue
                checked.add((module.__name__, name))
                with (
                    self.subTest(module=module.__name__, field=name),
                    patch.dict(os.environ, {}, clear=True),
                ):
                    self.assertGreater(getattr(cls(), name), 0)
                    expected = field.default + 1
                    os.environ[field.validation_alias] = str(expected)
                    self.assertEqual(getattr(cls(), name), expected)
                    for invalid in ("", "0", "-1", "nan", "inf", "private-test-value"):
                        os.environ[field.validation_alias] = invalid
                        with self.assertRaises(ValidationError) as failure:
                            cls()
                        self.assertNotIn("private-test-value", str(failure.exception))
        self.assertTrue(checked, "Numeric budget coverage must not silently disappear")

    def test_flags_retain_exact_one_comparison_at_consumers(self):
        consumers = {
            "agents/agents/codex/runtime.py": {"otel", "multi_agent"},
            "agents/agents/claude/credentials.py": {"mirror_host_login"},
            "agents/agents/opencode/activity/telemetry.py": {"otel"},
        }
        for relative, fields in consumers.items():
            tree = ast.parse((SOURCE / relative).read_text())
            compared = {
                node.left.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr in fields
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == "1"
                and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
            }
            self.assertEqual(compared, fields, relative)

    def test_fixed_protocol_pins_are_not_environment_fields(self):
        for module, cls in self.classes():
            self.assertFalse(
                {name.lower() for name in vars(module) if name.isupper()}
                & set(cls.model_fields)
            )
            for field in cls.model_fields:
                self.assertFalse(
                    any(
                        part in field
                        for part in (
                            "image",
                            "sha256",
                            "timeout",
                            "label",
                            "max_body",
                            "lease_seconds",
                        )
                    )
                )

    def test_dotenv_and_secret_directories_are_not_configuration_sources(self):
        from laomedo.skills.interface.sources.settings import Settings

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {}, clear=True),
        ):
            path = Path(directory)
            (path / ".env").write_text("LAOMEDO_SKILL_SOURCE_URL=http://unexpected\n")
            (path / "LAOMEDO_SKILL_SOURCE_URL").write_text("http://unexpected")
            self.assertEqual(
                Settings(_env_file=path / ".env", _secrets_dir=path).url, ""
            )

    def test_missing_viewer_paths_keep_keyerror(self):
        from laomedo.integrations.langflow.settings import Settings

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(KeyError, "LAOMEDO_SKILL_STORE"):
                Settings().required_path("skill_store")

    def test_raw_environment_boundaries_stay_explicit(self):
        protected = {
            "host/runner/utils.py": "os.environ.items()",
            "git/command.py": "os.environ.items()",
            "agents/agents/claude/policy.py": "env = dict(environment or {})",
            "agents/agents/claude/auth/utils.py": "os.environ if environment is None",
            "skills/sources/repository.py": "os.environ.items()",
            "agents/agents/codex/agent.py": "ConnectionSettings.environment_snapshot(None)",
            "host/publication/cli.py": "key in os.environ",
            "github/interface/issues/cli.py": "os.environ.get(args.github_token_env)",
            "github/interface/pull_requests/cli.py": "os.environ.get(args.github_token_env)",
            "agents/interface/bridge.py": '"LAOMEDO_" + provider.upper()',
        }
        for relative, expression in protected.items():
            self.assertIn(expression, (SOURCE / relative).read_text(), relative)
        helper = (SOURCE / "git/credential_helper.py").read_text()
        self.assertIn('os.environ.get("LAOMEDO_MEDIATED_GIT_TOKEN", "")', helper)
        self.assertNotIn("pydantic", helper)
        self.assertNotIn("import laomedo", helper)


class ErrorContractTests(unittest.TestCase):
    def test_each_domain_exception_has_a_documented_code_contract(self):
        for path in SOURCE.rglob("errors.py"):
            module = importlib.import_module(
                "laomedo." + ".".join(path.relative_to(SOURCE).with_suffix("").parts)
            )
            for node in ast.parse(path.read_text()).body:
                if not isinstance(node, ast.ClassDef):
                    continue
                cls = getattr(module, node.name)
                with self.subTest(exception=cls.__name__):
                    self.assertGreater(len(ast.get_docstring(node) or ""), 35)
                    if cls.__name__ == "RunnerResultError":
                        error = cls(
                            {
                                "run_id": "retained-run",
                                "error_category": "runner_transport_failed",
                            }
                        )
                        self.assertEqual(error.code, "runner_transport_failed")
                        self.assertEqual(error.run_reference["run_id"], "retained-run")
                        continue  # Graph invocation errors retain a record, unlike scalar domain errors.
                    if cls.__name__ == "GitCommandTimeout":
                        for cleanup in (False, True):
                            error = cls(["git"], 1, cleanup)
                            self.assertIsInstance(error, TimeoutExpired)
                            self.assertEqual(error.cleanup_verified, cleanup)
                            self.assertEqual(
                                error.code,
                                (
                                    "git_timeout"
                                    if cleanup
                                    else "git_timeout_cleanup_unverified"
                                ),
                            )
                            restored = pickle.loads(pickle.dumps(error))
                            self.assertEqual(type(restored), cls)
                            self.assertEqual(restored.__dict__, error.__dict__)
                            self.assertEqual(str(restored), str(error))
                        continue  # Native timeout protocol differs from scalar domain errors.
                    if cls.__name__ == "PushOutcomeUnknown":
                        error = cls("timeout", None)
                        code = "push_outcome_unknown"
                    else:
                        code = "existing_category"
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

        error = ConflictError("base_revision_changed")
        self.assertIsInstance(error, SkillStoreError)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.code, "base_revision_changed")
