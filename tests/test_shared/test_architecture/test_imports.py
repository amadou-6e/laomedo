"""Every internal from-import resolves to an owner on this independent source tree."""

import ast
from pathlib import Path
import unittest
from support.paths import repository_root


class InternalImportOwnerTests(unittest.TestCase):
    def test_eager_and_lazy_imports_have_current_module_owners(self):
        source = repository_root() / "src"
        paths = list((source / "laomedo").rglob("*.py"))
        self.assertTrue(paths, "The current source must actually be scanned")
        missing = []
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ImportFrom):
                    modules = [node.module] if node.module else []
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    continue
                for module in modules:
                    if not module.startswith("laomedo."):
                        continue
                    owner = source.joinpath(*module.split("."))
                    if (
                        not owner.with_suffix(".py").is_file()
                        and not (owner / "__init__.py").is_file()
                    ):
                        missing.append(
                            (path.relative_to(source).as_posix(), node.lineno, module)
                        )
        self.assertEqual(
            missing,
            [],
            "An independent cut must not import future feature owners, even lazily",
        )
