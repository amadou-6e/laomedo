"""Keep connection orchestration independent of framework and provider execution."""

import ast
import importlib
import unittest
from support.paths import repository_root


class ConnectionOwnershipTests(unittest.TestCase):
    def test_concrete_logins_are_defined_by_their_harness(self):
        for provider, name in (
            ("codex", "CodexConnection"),
            ("claude", "ClaudeConnection"),
            ("opencode", "GoConnection"),
        ):
            module = importlib.import_module(
                "laomedo.agents.agents." + provider + ".connection"
            )
            self.assertEqual(getattr(module, name).__module__, module.__name__)

    def test_connection_layers_do_not_acquire_framework_or_runtime_imports(self):
        source = repository_root() / "src/laomedo/agents"
        paths = list((source / "connections").glob("*.py"))
        paths += [
            source / "agents" / provider / "connection.py"
            for provider in ("codex", "claude", "opencode")
        ]
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(
                        (node.module or "").startswith(
                            ("langflow", "lfx", "fastapi", "laomedo.integrations")
                        ),
                        str(path),
                    )
                    if path.name == "connection.py":
                        self.assertNotIn(
                            node.module,
                            {
                                "laomedo.agents.connections.service",
                                "laomedo.agents.connections.controllers",
                            },
                            str(path),
                        )
            for node in tree.body:
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else []
                    )
                )
                self.assertFalse(
                    any(name.startswith(("py_docker", "acp")) for name in names),
                    str(path),
                )

    def test_private_host_storage_dependencies_are_explicit(self):
        source = repository_root() / "src/laomedo/agents"
        allowed = {
            "connections/service.py": {
                "_atomic_private",
                "_outside_git",
                "_restrict_windows_directory",
                "_locked",
            },
            "connections/controllers.py": {"_outside_git"},
            "agents/codex/connection.py": {"_atomic_private", "_locked"},
            "agents/claude/connection.py": {
                "_atomic_private",
                "_restrict_windows_directory",
            },
            "agents/opencode/connection.py": {
                "_atomic_private",
                "_restrict_windows_directory",
            },
        }
        for relative, names in allowed.items():
            tree = ast.parse((source / relative).read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "laomedo.host.credentials.siwc.utils"
                for alias in node.names
                if alias.name.startswith("_")
            }
            self.assertLessEqual(imported, names, relative)
