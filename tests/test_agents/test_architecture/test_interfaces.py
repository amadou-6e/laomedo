"""Keep Agent leaves discoverable and imports bound to defining symbols."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest
from support.model_contracts import assert_described_models
from support.paths import repository_root

ROOT = repository_root() / "src/laomedo"


class AgentModuleStructureTests(unittest.TestCase):
    def test_provider_entrypoint_exports_canonical_top_level_contracts(self):
        """Provider imports expose each defining contract once, without duplicate types."""
        from importlib import import_module
        from laomedo.agents.agents import base

        owner = ROOT / "agents/agents/base"
        expected = {}
        for path in owner.glob("*.py"):
            if path.name == "interim.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and any(
                    isinstance(parent, ast.Name) and parent.id in {"ABC", "Protocol"}
                    for parent in node.bases
                ):
                    expected[node.name] = base.__name__ + "." + path.stem
        self.assertTrue(expected, "The contract scan must not be empty")
        self.assertEqual(set(base.__all__), set(expected))
        for name, module in expected.items():
            with self.subTest(contract=name):
                exported = getattr(base, name)
                self.assertIs(exported, getattr(import_module(module), name))
                self.assertEqual(exported.__module__, module)

    def test_public_contract_import_does_not_load_native_provider_integrations(self):
        """The provider-authoring entry point needs no native SDK or provider startup."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from laomedo.agents.agents import base; "
                "unexpected = [name for name in sys.modules if name.startswith("
                "('py_docker', 'agent_client_protocol', "
                "'laomedo.agents.agents.codex', 'laomedo.agents.agents.claude', "
                "'laomedo.agents.agents.opencode'))]; "
                "assert not unexpected, unexpected; assert base.__all__",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_value_package_has_one_defining_owner_and_no_facade_exports(self):
        """Values remain concern-owned; public base exports do not duplicate models."""
        package = ROOT / "agents/agents/base/models"
        self.assertTrue(package.is_dir())
        self.assertFalse(package.with_suffix(".py").exists())
        tree = ast.parse((package / "__init__.py").read_text(encoding="utf-8"))
        self.assertFalse(
            any(
                isinstance(
                    node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef)
                )
                for node in tree.body
            )
        )

    def test_internal_values_import_definitions_without_public_initializer_cycles(self):
        """Internal concerns bypass the public aggregator; external authors may use it."""
        owner = ROOT / "agents/agents/base"
        for path in ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(
                        node.module,
                        "laomedo.agents.agents.base.models",
                        (path, node.lineno),
                    )
                    if path.is_relative_to(owner) and path != owner / "__init__.py":
                        self.assertNotEqual(
                            node.module,
                            "laomedo.agents.agents.base",
                            (path, node.lineno),
                        )

    def test_public_interface_does_not_import_provider_implementations(self):
        paths = list((ROOT / "agents/interface").rglob("*.py"))
        self.assertTrue(paths, "Public interface scan must not be empty")
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                names = (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                )
                for name in names:
                    self.assertFalse(
                        name == "laomedo.agents.agents"
                        or name.startswith("laomedo.agents.agents."),
                        (path, node.lineno, name),
                    )
        models = ast.parse((ROOT / "agents/interface/models.py").read_text())
        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("laomedo.")
                and node.module != "laomedo.agents.registry"
                or isinstance(node, ast.Import)
                and any(item.name.startswith("laomedo.") for item in node.names)
                for node in ast.walk(models)
            )
        )

    def test_retired_module_files_and_owner_directories_stay_absent(self):
        mapping = json.loads(
            (ROOT.parents[1] / "tools/migrations/module-paths.json").read_text()
        )
        self.assertTrue(mapping)
        reused_packages = set()
        for old in mapping:
            path = ROOT.parent.joinpath(*old.split("."))
            self.assertFalse(path.with_suffix(".py").exists(), old)
            if (path / "__init__.py").is_file():
                reused_packages.add(old)
        # This former flat module now owns a real package, not a forwarder.
        self.assertEqual(reused_packages, {"laomedo.agents.artifacts"})
        for retired in (
            "agents/providers",
            "agents/runtime",
            "agents/protocol",
            "agents/contracts",
            "agents/workflow",
            "agents/feedback",
            "agents/handoffs",
            "activity",
        ):
            self.assertEqual(list((ROOT / retired).rglob("*.py")), [], retired)

    def test_agent_record_fields_keep_their_descriptions(self):
        assert_described_models(
            "agents.models",
            "agents.artifacts.models",
            "agents.orchestration.models",
            "agents.agents.base.models.invocation",
            "agents.agents.base.models.catalog",
            "agents.agents.base.models.commands",
            "agents.agents.base.models.credentials",
            "agents.agents.base.models.failures",
            "agents.agents.base.models.journal",
            "agents.agents.base.models.preparation",
            "agents.agents.base.models.runtime",
            "agents.interface.models",
            "agents.activity.models",
            "agents.agents.claude.activity.models",
            "agents.agents.opencode.activity.models",
            "agents.agents.opencode.models",
            "agents.agents.claude.auth.models",
            "host.leases.models",
            "host.private_state.models",
        )

    def module_imports(self, path, tree):
        """Find both ordinary and from-import module bindings in owned source."""
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(
                    i.name for i in node.names if i.name.startswith("laomedo.")
                )
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = path.parent
                    for _ in range(node.level - 1):
                        parent = parent.parent
                    base = (
                        parent.joinpath(*(node.module or "").split("."))
                        if node.module
                        else parent
                    )
                elif (node.module or "").startswith("laomedo."):
                    base = ROOT.parent.joinpath(*node.module.split("."))
                else:
                    continue
                for item in node.names:
                    candidate = base / item.name
                    if (
                        candidate.with_suffix(".py").is_file()
                        or (candidate / "__init__.py").is_file()
                    ):
                        found.append(str(candidate))
        return found

    def test_module_binding_guard_detects_from_aliases_and_relative_modules(self):
        path = ROOT / "agents/agents/codex/agent.py"
        for source in (
            "import laomedo.agents.errors as e",
            "from laomedo.agents import errors as e",
            "from . import settings as config",
        ):
            self.assertTrue(self.module_imports(path, ast.parse(source)), source)
        self.assertFalse(
            self.module_imports(
                path, ast.parse("from laomedo.agents.errors import RunnerError")
            )
        )

    def test_owned_agent_files_use_direct_symbols_and_module_level_classes(self):
        paths = list((ROOT / "agents").rglob("*.py"))
        self.assertTrue(paths, "The real Agent owner must be scanned")
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            top_classes = {id(n) for n in tree.body if isinstance(n, ast.ClassDef)}
            self.assertEqual(self.module_imports(path, tree), [], path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.assertIn(id(node), top_classes, (path, node.lineno))
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        any(i.name.startswith("laomedo.") for i in node.names),
                        (path, node.lineno),
                    )

    def test_class_owning_agent_leaves_have_an_interface_readme(self):
        paths = list((ROOT / "agents").rglob("*.py"))
        self.assertTrue(paths, "The real Agent owner must be scanned")
        for path in paths:
            tree = ast.parse(path.read_text())
            if any(isinstance(node, ast.ClassDef) for node in tree.body):
                self.assertTrue(path.with_name("README.md").is_file(), path)

    def test_retired_codex_server_generation_requires_explicit_manual_migration(self):
        from test_shared.test_migration.utils import load_migration

        migration = load_migration()
        owner = "laomedo.agents.providers.codex.servers"
        for source in (
            f"import {owner}\n",
            f"from {owner} import AppServer\n",
            f"from {owner} import *\n",
            f"import {owner} as legacy\nlegacy.AppServer(**options)\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(migration.ManualMigrationRequired):
                    migration.migrate_source(source)
