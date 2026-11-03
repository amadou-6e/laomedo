"""Keep test-bearing folders discoverable by their test_ prefix."""

from pathlib import Path
import unittest

from support.paths import repository_root


class TestLayoutTests(unittest.TestCase):
    def test_owned_concerns_do_not_return_as_flat_prefix_families(self):
        root = repository_root() / "tests"
        forbidden = sorted(
            path.name
            for pattern in (
                "test_bundle_*.py",
                "test_verified_stage.py",
                "test_skill_*.py",
                "test_workspace_skill*.py",
            )
            for path in root.glob(pattern)
        )
        self.assertEqual(forbidden, [], "Put owned cases in their concern packages")
        for retired in (
            "git_runner_controls.py",
            "retained_shared.py",
            "test_browser/skill_files.cjs",
            "test_browser/skill_sources.cjs",
        ):
            self.assertFalse((root / retired).exists(), retired)

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
