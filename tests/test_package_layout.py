"""Protect installed resources and legacy entrypoints during src migration."""
import ast
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from laomedo._paths import import_root, package_root

ROOT = Path(__file__).resolve().parents[1]


class PackageLayoutTests(unittest.TestCase):
    def test_canonical_runner_imports_in_a_fresh_process(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        result = subprocess.run(
            [sys.executable, "-c",
             "import laomedo.agents.local_runner as runner; print(runner.__name__)"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "laomedo.agents.local_runner")

    def test_every_legacy_module_has_one_identity_and_globals(self):
        mapping = json.loads((ROOT / "tools/package-layout.json").read_text())
        for legacy, canonical in mapping.items():
            with self.subTest(module=legacy):
                try:
                    old = importlib.import_module(legacy)
                except ModuleNotFoundError as error:
                    if (error.name or "").split(".")[0] in {"fastapi", "starlette", "lfx", "langflow"}:
                        self.skipTest(f"Optional app dependency is not installed: {error.name}")
                    raise
                new = importlib.import_module(canonical)
                self.assertIs(old, new)
                self.assertIs(old.__dict__, new.__dict__)
        from laomedo.local_runner import RunnerError
        from laomedo.agents.local_runner import RunnerError as CanonicalError
        self.assertIs(RunnerError, CanonicalError)

    def test_legacy_mock_intercepts_real_server_factory(self):
        from laomedo.agents.local_runner import serve
        marker = object()
        with patch.dict(os.environ, {"LAOMEDO_STARTUP_GATE": ""}):
            with patch("laomedo.local_runner.ThreadingHTTPServer", return_value=marker) as server:
                self.assertIs(serve(object(), port=0), marker)
                server.assert_called_once()

    def test_pinned_package_resources_match_checkout_bytes(self):
        source = ROOT / "src/laomedo"
        files = ["runner-config.toml", "agent_mediation_client.mjs",
                 "agent_gh_adapter.mjs", "agent_git_remote.mjs",
                 "resources/codex-seccomp.json", "resources/bundle_stage.sh",
                 "resources/skills/skill-summary/SKILL.md", "git_credential_helper.py"]
        for name in files:
            with self.subTest(resource=name):
                self.assertEqual(package_root().joinpath(name).read_bytes(),
                                 source.joinpath(name).read_bytes())
        from laomedo.local_runner import CONFIG, SECCOMP, MEDIATION_CLIENT
        self.assertEqual(CONFIG, package_root() / "runner-config.toml")
        self.assertEqual(SECCOMP, package_root() / "resources/codex-seccomp.json")
        self.assertEqual(MEDIATION_CLIENT, package_root() / "agent_mediation_client.mjs")
        self.assertTrue((import_root() / "laomedo/work_graph/stage_worker.py").is_file())

    def test_checkout_bridge_has_no_runtime_or_initialisation_divergence(self):
        source = ast.parse((ROOT / "src/laomedo/__init__.py").read_text())
        self.assertEqual(len(source.body), 1, "Add bridge parity before package initialisation code")
        self.assertIsInstance(source.body[0], ast.Expr)
        self.assertIsInstance(source.body[0].value, ast.Constant)
        bridge = ast.parse((ROOT / "laomedo/__init__.py").read_text())
        self.assertFalse(any(isinstance(n, (ast.ClassDef, ast.FunctionDef)) for n in bridge.body))

    def test_stage_accepts_legacy_checkout_and_installed_import_roots(self):
        from laomedo.work_graph.docker_stage import DockerLangflowStage
        flow = json.loads((ROOT / "tests/fixtures/pre-src-native-flow.json").read_text())
        checkout = DockerLangflowStage(flow, source_root=ROOT)
        direct = DockerLangflowStage(flow)
        self.assertEqual(checkout.source_root, ROOT / "src")
        self.assertEqual(direct.source_root, import_root())
        self.assertIn(str(ROOT / "src/laomedo"), " ".join(checkout._command("check", ROOT, "validate")))

    def test_legacy_process_entrypoints_run_main_from_checkout(self):
        # Fresh process deliberately has no source PYTHONPATH or editable install.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));module=sys.argv.pop(1);sys.argv[0]=module;runpy.run_module(module,run_name='__main__')"
        for module in ("managed_service", "local_runner", "claude_runner", "container_lease"):
            commands = [[sys.executable, "-m", "laomedo." + module, "--help"]]
            if module in ("local_runner", "claude_runner"):
                commands.append([sys.executable, "-c", bootstrap, str(import_root()),
                                 "laomedo." + module, "--help"])
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                            text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout.lower())
                    self.assertNotIn("found in sys.modules", result.stderr)
        result = subprocess.run([sys.executable, "-m", "laomedo.work_graph.stage_worker", "invalid"],
                                cwd=ROOT, env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2)

    def test_source_cli_works_from_unrelated_directory(self):
        # The same command is also exercised against the installed wheel by the
        # external wheel check; here source visibility is explicit and local.
        bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));sys.argv=['laomedo.work_graph','--help'];runpy.run_module('laomedo.work_graph',run_name='__main__')"
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, "-c", bootstrap, str(import_root())],
                                    cwd=cwd, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())
