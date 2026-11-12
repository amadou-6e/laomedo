"""Protect canonical ownership, packaged resources and executable entrypoints."""

import ast
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support.paths import repository_root
from laomedo._paths import import_root
from laomedo._paths import package_root

ROOT = repository_root()


class PackageLayoutTests(unittest.TestCase):
    def test_installed_package_matches_current_source_files(self):
        """Check the real installed artifact, including stale resources and modules."""
        source = ROOT.joinpath("src/laomedo").resolve()
        installed = package_root().resolve()
        if source == installed:
            self.skipTest("Install the wheel and run outside the source checkout")
        modules = set()
        manifest = json.loads((ROOT / "docker/images.json").read_text(encoding="utf-8"))
        build_inputs = {Path("images.json"): ROOT / "docker/images.json"}
        for registration in manifest.values():
            for name in registration["files"]:
                relative = Path(registration["context"]) / name
                build_inputs[relative] = ROOT / "docker" / relative
        installed_inputs = set()
        for artifact in installed.rglob("*"):
            if not artifact.is_file() or "__pycache__" in artifact.parts:
                continue
            relative = artifact.relative_to(installed)
            if relative.parts[:2] == ("container_images", "resources"):
                resource = Path(*relative.parts[2:])
                with self.subTest(build_input=resource.as_posix()):
                    self.assertIn(
                        resource,
                        build_inputs,
                        "Unregistered Docker input in installed wheel",
                    )
                    self.assertEqual(
                        artifact.read_bytes(), build_inputs[resource].read_bytes()
                    )
                installed_inputs.add(resource)
                continue
            current = source / relative
            with self.subTest(artifact=relative.as_posix()):
                self.assertTrue(
                    current.is_file(),
                    "Installed artifact has no current source: " + str(relative),
                )
                if artifact.suffix == ".py":
                    modules.add(relative)
                    # Python decodes source with universal newlines. Registry
                    # bundles and packaged data retain their separate byte checks.
                    self.assertEqual(
                        artifact.read_text(encoding="utf-8-sig"),
                        current.read_text(encoding="utf-8-sig"),
                        "Installed Python differs from current source: "
                        + str(relative),
                    )
        self.assertEqual(
            installed_inputs,
            set(build_inputs),
            "Wheel must include every registered Docker input",
        )
        self.assertEqual(
            modules,
            {module.relative_to(source) for module in source.rglob("*.py")},
            "The installed wheel must contain every current Python module",
        )

    def test_package_root_has_only_shared_infrastructure(self):
        self.assertEqual(
            {p.name for p in package_root().iterdir() if p.is_file()} - {"README.md"},
            {"__init__.py", "_paths.py", "docker.py"},
        )

    def test_canonical_modules_import_without_forwarders(self):
        mapping = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
        for canonical in mapping.values():
            with self.subTest(module=canonical):
                try:
                    if canonical.startswith(
                        (
                            "laomedo.integrations.langflow.",
                            "laomedo.agents.interface.langflow.",
                        )
                    ):
                        # Bootstrap the installed compatibility shim before its
                        # LFX plugins, as the real app and graph CLI do. Core
                        # modules do not acquire a framework dependency.
                        importlib.import_module("langflow")
                    module = importlib.import_module(canonical)
                except ModuleNotFoundError as error:
                    if (error.name or "").split(".")[0] in {
                        "acp",
                        "fastapi",
                        "starlette",
                        "lfx",
                        "langflow",
                    }:
                        self.skipTest("Optional app dependencies are not installed")
                    raise
                self.assertEqual(module.__name__, canonical)
                self.assertNotIn("alias_module", Path(module.__file__).read_text())

    def test_resource_owners_and_bytes(self):
        from laomedo.agents.agents.codex.settings import CONFIG
        from laomedo.agents.agents.codex.settings import SECCOMP
        from laomedo.agents.agents.codex.settings import MEDIATION_CLIENT
        from laomedo.host.publication.bundle.settings import SCRIPT

        paths = [
            CONFIG,
            SECCOMP,
            MEDIATION_CLIENT,
            SCRIPT,
            MEDIATION_CLIENT.with_name("agent_gh_adapter.mjs"),
            MEDIATION_CLIENT.with_name("agent_git_remote.mjs"),
            package_root() / "skills/resources/skill-summary/SKILL.md",
            package_root() / "git/credential_helper.py",
        ]
        for path in paths:
            self.assertEqual(
                path.read_bytes(),
                (ROOT / "src/laomedo" / path.relative_to(package_root())).read_bytes(),
            )
        self.assertEqual(
            CONFIG.parent, package_root() / "agents/agents/codex/resources"
        )
        self.assertEqual(SECCOMP.parent, CONFIG.parent)
        self.assertEqual(
            MEDIATION_CLIENT.parent, package_root() / "host/mediation/resources"
        )
        self.assertEqual(SCRIPT.parent, package_root() / "host/publication/resources")

    def test_canonical_clis_work_outside_checkout(self):
        env = dict(os.environ, PYTHONPATH=str(import_root()))
        modules = [
            "laomedo.host.managed_service",
            "laomedo.agents.agents.codex.cli",
            "laomedo.agents.agents.claude.cli",
            "laomedo.host.leases.process_cli",
            "laomedo.host.leases.service_cli",
            "laomedo.work_graph",
        ]
        with tempfile.TemporaryDirectory() as cwd:
            for module in modules:
                with self.subTest(module=module):
                    result = subprocess.run(
                        [sys.executable, "-m", module, "--help"],
                        cwd=cwd,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout.lower())
                    self.assertNotIn("found in sys.modules", result.stderr)

    def test_stage_accepts_checkout_src_and_installed_roots(self):
        from laomedo.work_graph.docker_stage import DockerLangflowStage

        flow = json.loads(
            (ROOT / "tests/fixtures/pre-src-native-flow.json").read_text()
        )
        self.assertEqual(
            DockerLangflowStage(flow, source_root=ROOT).source_root, ROOT / "src"
        )
        self.assertEqual(DockerLangflowStage(flow).source_root, import_root())

    def test_agent_class_members_follow_public_api_order(self):
        """Keep provider entrypoints discoverable before implementation helpers.

        Inspect source without importing optional runtimes. Properties and their
        accessors form one section; public class/static methods remain public.
        Class fields and decorators retain their separate runtime semantics.
        """
        agent_root = ROOT / "src/laomedo/agents"
        paths = list(agent_root.rglob("*.py"))
        self.assertTrue(paths, "Agent class ordering scan must find source files")
        agent_classes = 0
        paths.extend(
            ROOT.joinpath("components/laomedo", name + ".py")
            for name in ("bounded_controller", "github_pr", "output_contract", "skill")
        )
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for definition in ast.walk(tree):
                if not isinstance(definition, ast.ClassDef):
                    continue
                if path.is_relative_to(agent_root):
                    agent_classes += 1
                sections = []
                dunders = []
                for method in definition.body:
                    if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if method.name.startswith("__") and method.name.endswith("__"):
                        section = 0
                        dunders.append(method.name)
                    elif any(
                        isinstance(decorator, ast.Name)
                        and decorator.id == "property"
                        or isinstance(decorator, ast.Attribute)
                        and decorator.attr in {"setter", "getter", "deleter"}
                        for decorator in method.decorator_list
                    ):
                        section = 1
                    else:
                        section = 3 if method.name.startswith("_") else 2
                    sections.append(section)
                with self.subTest(path=path.relative_to(ROOT), cls=definition.name):
                    self.assertEqual(
                        sections,
                        sorted(sections),
                        "Expected dunders, properties, public methods, private helpers",
                    )
                    if "__init__" in dunders:
                        self.assertEqual(dunders[0], "__init__")
        self.assertGreater(
            agent_classes, 0, "Agent scan must inspect class definitions"
        )
