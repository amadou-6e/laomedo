"""The graph join protocol has a discoverable module-level handler owner."""

import ast
from pathlib import Path
import unittest
from support.paths import repository_root
from laomedo.integrations.langflow.join.handler import JoinRequestHandler
from laomedo.integrations.langflow.join.server import JoinServer


class JoinHandlerStructureTests(unittest.TestCase):
    def test_handler_is_module_level_and_server_binds_its_own_context(self):
        root = repository_root() / "src/laomedo/integrations/langflow/join"
        paths = list(root.glob("*.py"))
        self.assertTrue(paths, "The actual join owner must be scanned")
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(
                        any(
                            isinstance(child, ast.ClassDef) for child in ast.walk(node)
                        ),
                        path,
                    )
        self.assertEqual(
            JoinRequestHandler.__module__, "laomedo.integrations.langflow.join.handler"
        )
        self.assertEqual(
            JoinServer.__module__, "laomedo.integrations.langflow.join.server"
        )
