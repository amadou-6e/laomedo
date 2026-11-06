"""Protect defining Skill owners and the domain's dependency direction."""

import ast
import unittest

from support.paths import repository_root
from support.model_contracts import assert_described_models


class SkillOwnershipTests(unittest.TestCase):
    def test_skill_record_fields_keep_their_descriptions(self):
        assert_described_models("skills.registry.models", "skills.operations.models")

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
            "operations/settings.py",
            "workspace/utils.py",
            "ingestion/utils.py",
        ):
            with self.subTest(retired=name):
                self.assertFalse((root / name).exists())
