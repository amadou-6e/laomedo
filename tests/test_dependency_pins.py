"""Keep the temporary Git-pinned runner dependency identical in frozen installs."""

from pathlib import Path
import re
import unittest


class DependencyPinTests(unittest.TestCase):
    def test_runner_extra_and_frozen_lock_resolve_the_same_revision(self):
        root = Path(__file__).resolve().parents[1]
        pattern = re.compile(r"https://github\.com/amadou-6e/py-docker\.git(?:@|\?rev=)([0-9a-f]{40})(?:#([0-9a-f]{40}))?")
        configured = pattern.findall(root.joinpath("pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(len(configured), 1)
        expected = configured[0][0]
        locked = pattern.findall(root.joinpath("uv.lock").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(locked), 2)
        self.assertTrue(any(resolved for _, resolved in locked))
        self.assertTrue(all(requested == expected and (not resolved or resolved == expected) for requested, resolved in locked))
