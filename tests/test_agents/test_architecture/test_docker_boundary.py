"""Keep agent container lifecycles behind their shared Docker implementation."""

import ast
import unittest

from support.paths import repository_root


class DockerBoundaryTests(unittest.TestCase):
    """Detect bypasses in any current or newly added agent provider."""

    def test_native_rollout_export_cannot_restore_cli_subprocess_dispatch(self):
        path = (
            repository_root()
            / "src/laomedo/agents/agents/codex/activity/rollout_export.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        )
        self.assertNotIn("subprocess", imports)

    def test_only_shared_runtime_constructs_clients_or_dispatches_container_work(self):
        root = repository_root() / "src/laomedo"
        owner = root / "docker.py"
        paths = list(root.rglob("*.py"))
        self.assertTrue(paths, "Docker boundary scan must not be empty")
        violations = []
        for path in paths:
            if path == owner:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module in {
                    "py_docker",
                    "py_docker.client",
                    "docker",
                    "docker.client",
                }:
                    if any(
                        name.name in {"Client", "DockerClient", "APIClient", "from_env"}
                        for name in node.names
                    ):
                        violations.append((path, node.lineno, "native Client import"))
                if isinstance(node, ast.Import):
                    if any(name.name in {"py_docker", "docker"} for name in node.names):
                        violations.append((path, node.lineno, "native SDK import"))
                if not isinstance(node, ast.Call) or not isinstance(
                    node.func, ast.Attribute
                ):
                    continue
                service = node.func.value
                if isinstance(service, ast.Attribute) and (
                    service.attr,
                    node.func.attr,
                ) in {
                    ("jobs", "run"),
                    ("jobs", "recover"),
                    ("sessions", "open"),
                    ("sessions", "recover"),
                    ("execution", "run"),
                    ("containers", "watch"),
                    ("containers", "create"),
                    ("containers", "start"),
                    ("containers", "stop"),
                    ("containers", "remove"),
                }:
                    violations.append((path, node.lineno, "direct container operation"))
        self.assertEqual(violations, [], str(violations))
