"""Keep test-bearing folders discoverable by their test_ prefix."""

from pathlib import Path
import unittest

from support.paths import repository_root


class TestLayoutTests(unittest.TestCase):
    def test_test_bearing_folders_use_the_test_prefix(self):
        root = repository_root() / "tests"
        folders = set()
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if not (
                path.name.startswith("test_")
                and path.suffix in {".py", ".mjs"}
                or path.suffix == ".cjs"
            ):
                continue
            folders.update(path.relative_to(root).parents)
        invalid = sorted(
            folder.as_posix()
            for folder in folders
            if folder != Path(".") and not folder.name.startswith("test_")
        )
        self.assertEqual(invalid, [], "Test folders must start with test_")
