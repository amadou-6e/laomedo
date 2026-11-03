"""Protect canonical ownership, packaged resources and executable entrypoints."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from laomedo._paths import import_root
from laomedo._paths import package_root

ROOT = Path(__file__).resolve().parents[1]


class PackageLayoutTests(unittest.TestCase):
    def test_retired_module_files_cannot_return_even_in_an_editable_checkout(self):
        retired = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
        self.assertTrue(retired)
        for name in retired:
            path = package_root().parent.joinpath(*name.split(".")).with_suffix(".py")
            self.assertFalse(path.exists(), name)

    def test_installed_package_matches_current_source_files(self):
        """Check the real installed artifact, including stale resources and modules."""
        source = ROOT.joinpath("src/laomedo").resolve()
        installed = package_root().resolve()
        if source == installed:
            self.skipTest("Install the wheel and run outside the source checkout")
        modules = set()
        for artifact in installed.rglob("*"):
            if not artifact.is_file() or "__pycache__" in artifact.parts:
                continue
            relative = artifact.relative_to(installed)
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
            modules,
            {module.relative_to(source) for module in source.rglob("*.py")},
            "The installed wheel must contain every current Python module",
        )

    def test_package_root_has_only_shared_infrastructure(self):
        self.assertEqual(
            {p.name for p in package_root().iterdir() if p.is_file()} - {"README.md"},
            {"__init__.py", "_paths.py"},
        )
        self.assertTrue((ROOT / "src/laomedo/README.md").is_file())

    def test_canonical_modules_import_without_forwarders(self):
        mapping = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
        for canonical in mapping.values():
            with self.subTest(module=canonical):
                try:
                    module = importlib.import_module(canonical)
                except ModuleNotFoundError as error:
                    if error.name == "acp" and canonical in {
                        "laomedo.agents.agents.base.acp.session",
                        "laomedo.agents.agents.base.acp.transport",
                    }:
                        self.skipTest("Optional runner ACP dependency is not installed")
                    if (error.name or "").split(".")[0] in {
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
            package_root() / "git/credentials/helper.py",
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
