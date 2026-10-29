"""Prevent retired provider communication paths from returning beside ACP."""

import ast
from pathlib import Path
import unittest

from laomedo._paths import package_root


class AcpBoundaryTests(unittest.TestCase):
    def test_retired_opencode_producers_and_http_client_are_removed(self):
        root = package_root()
        for name in ("events.py", "settings.py", "utils.py"):
            self.assertFalse((root / "activity/opencode" / name).exists())
        runner = ast.parse((root / "agents/providers/opencode/runner.py").read_text())
        self.assertFalse(
            any(
                isinstance(node, ast.ClassDef) and node.name == "OpenCodeHTTP"
                for node in ast.walk(runner)
            )
        )
        retired = {
            "laomedo.activity.opencode.events",
            "laomedo.activity.opencode.utils",
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
