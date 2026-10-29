"""Protect canonical ownership, packaged resources and executable entrypoints."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from laomedo._paths import import_root; from laomedo._paths import package_root

ROOT = Path(__file__).resolve().parents[1]


class PackageLayoutTests(unittest.TestCase):
    def test_installed_package_has_no_retired_python_modules(self):
        """Catch stale build output copied into an otherwise successful wheel."""
        source = ROOT.joinpath("src/laomedo")
        for module in package_root().rglob("*.py"):
            with self.subTest(module=module):
                self.assertTrue(source.joinpath(module.relative_to(package_root())).is_file(),
                                "Installed module has no current source: " + str(module))

    def test_package_root_has_only_shared_infrastructure(self):
        self.assertEqual({p.name for p in package_root().iterdir() if p.is_file()}, {"__init__.py", "_paths.py"})

    def test_canonical_modules_import_without_forwarders(self):
        mapping = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
        for canonical in mapping.values():
            with self.subTest(module=canonical):
                try:
                    module = importlib.import_module(canonical)
                except ModuleNotFoundError as error:
                    if (error.name or "").split(".")[0] in {"fastapi", "starlette", "lfx", "langflow"}:
                        self.skipTest("Optional app dependencies are not installed")
                    raise
                self.assertEqual(module.__name__, canonical)
                self.assertNotIn("alias_module", Path(module.__file__).read_text())

    def test_resource_owners_and_bytes(self):
        from laomedo.agents.agents.codex.settings import CONFIG; from laomedo.agents.agents.codex.settings import SECCOMP; from laomedo.agents.agents.codex.settings import MEDIATION_CLIENT
        from laomedo.host.publication.bundle.settings import SCRIPT
        paths = [CONFIG, SECCOMP, MEDIATION_CLIENT, SCRIPT,
                 MEDIATION_CLIENT.with_name("agent_gh_adapter.mjs"), MEDIATION_CLIENT.with_name("agent_git_remote.mjs"),
                 package_root() / "skills/resources/skill-summary/SKILL.md",
                 package_root() / "git/credentials/helper.py"]
        for path in paths:
            self.assertEqual(path.read_bytes(), (ROOT / "src/laomedo" / path.relative_to(package_root())).read_bytes())
        self.assertEqual(CONFIG.parent, package_root() / "agents/agents/codex/resources")
        self.assertEqual(SECCOMP.parent, CONFIG.parent)
        self.assertEqual(MEDIATION_CLIENT.parent, package_root() / "host/mediation/resources")
        self.assertEqual(SCRIPT.parent, package_root() / "host/publication/resources")

    def test_canonical_clis_work_outside_checkout(self):
        env = dict(os.environ, PYTHONPATH=str(import_root()))
        modules = ["laomedo.host.managed_service", "laomedo.agents.agents.codex.cli", "laomedo.agents.agents.claude.cli",
                   "laomedo.host.leases.process_cli", "laomedo.host.leases.service_cli", "laomedo.work_graph"]
        with tempfile.TemporaryDirectory() as cwd:
            for module in modules:
                with self.subTest(module=module):
                    result = subprocess.run([sys.executable, "-m", module, "--help"], cwd=cwd, env=env,
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout.lower())
                    self.assertNotIn("found in sys.modules", result.stderr)

    def test_stage_accepts_checkout_src_and_installed_roots(self):
        from laomedo.work_graph.docker_stage import DockerLangflowStage
        flow = json.loads((ROOT / "tests/fixtures/pre-src-native-flow.json").read_text())
        self.assertEqual(DockerLangflowStage(flow, source_root=ROOT).source_root, ROOT / "src")
        self.assertEqual(DockerLangflowStage(flow).source_root, import_root())
