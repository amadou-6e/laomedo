"""Protect defining Skill owners and the domain's dependency direction."""

import ast
import unittest

from support.paths import repository_root


class SkillOwnershipTests(unittest.TestCase):
    def test_skill_domain_uses_defining_symbols_and_keeps_its_boundary(self):
        root = repository_root() / "src/laomedo/skills"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(module=path.relative_to(root).as_posix()):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        self.assertFalse(
                            any(
                                item.name.startswith("laomedo.") for item in node.names
                            ),
                            "Import the defining Skill object or function directly",
                        )
                    if isinstance(node, ast.ImportFrom) and node.module:
                        self.assertFalse(
                            node.module.startswith(
                                (
                                    "laomedo.agents.",
                                    "laomedo.host.",
                                    "laomedo.github.",
                                    "laomedo.work_graph.",
                                )
                            ),
                            "General Skills must not acquire caller-owned execution responsibilities",
                        )

    def test_retired_skill_owners_do_not_return_as_facades(self):
        root = repository_root() / "src/laomedo/skills"
        for name in (
            "registry/utils.py",
            "sources/client.py",
            "sources/server.py",
            "sources/cli.py",
            "operations/client.py",
            "operations/server.py",
            "operations/cli.py",
            "workspace/utils.py",
            "ingestion/utils.py",
        ):
            with self.subTest(retired=name):
                self.assertFalse((root / name).exists())

    def test_operation_settings_do_not_restore_the_retired_http_configuration(self):
        """Domain failure vocabulary is distinct from interface-owned URL/token settings."""
        path = repository_root() / "src/laomedo/skills/operations/settings.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        self.assertFalse(
            any(
                isinstance(
                    node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef)
                )
                for node in tree.body
            )
        )
        self.assertEqual(
            {node.targets[0].id for node in tree.body if isinstance(node, ast.Assign)},
            {"MANUAL_ERROR_CODES"},
        )
