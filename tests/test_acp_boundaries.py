"""Prevent retired provider communication paths from returning beside ACP."""

import ast
from pathlib import Path
import unittest

from laomedo._paths import package_root


class AcpBoundaryTests(unittest.TestCase):
    def test_codex_native_wire_and_parallel_turn_loops_are_retired(self):
        root = package_root()
        for relative in ("agents/agents/codex/native/base.py", "agents/agents/codex/native/server.py", "agents/agents/codex/split/server.py"):
            self.assertFalse((root / relative).exists())
        for relative in ("agents/agents/codex/agent.py", "agents/agents/codex/controller/service.py", "agents/agents/codex/split/executor.py"):
            tree = ast.parse((root / relative).read_text(encoding="utf-8-sig"))
            methods = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            self.assertFalse(methods.intersection({"wait_turn", "interrupt", "_read_frames", "request", "notify"}))
        self.assertFalse((root.parent.parent / "docker/codex-git/Dockerfile").exists())

    def test_retired_opencode_producers_and_http_client_are_removed(self):
        root = package_root()
        # These intentionally name the ACTUAL retired producer location. Do not
        # rewrite the historical names when moving current provider packages.
        for name in ("events.py", "settings.py", "utils.py"):
            self.assertFalse((root / "activity/opencode" / name).exists())
        runner = ast.parse((root / "agents/agents/opencode/agent.py").read_text())
        self.assertFalse(
            any(
                isinstance(node, ast.ClassDef) and node.name == "OpenCodeHTTP"
                for node in ast.walk(runner)
            )
        )
        retired = {
            "laomedo.activity.opencode.events",
            "laomedo.activity.opencode.utils",
            "laomedo.opencode_events",
            "laomedo.opencode_activity",
        }
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        retired.intersection(alias.name for alias in node.names),
                        str(path),
                    )
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, retired, str(path))
