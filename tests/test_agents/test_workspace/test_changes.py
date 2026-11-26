"""Verified source-to-snapshot change projection."""

from pathlib import Path
import tempfile
import unittest

from laomedo.agents.errors import RunnerError
from laomedo.agents.workspaces.changes import verified_changes
from laomedo.agents.workspaces.utils import _hash_tree


class VerifiedChangesTests(unittest.TestCase):
    def test_real_snapshots_produce_patch_and_reject_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (before / "example.py").write_text("value = 1\n", encoding="utf-8")
            (after / "example.py").write_text("value = 2\n", encoding="utf-8")
            source_hash, post_run_hash = _hash_tree(before), _hash_tree(after)
            patch = verified_changes(
                before, after, source_hash=source_hash, post_run_hash=post_run_hash
            )
            self.assertIn("-value = 1", patch)
            self.assertIn("+value = 2", patch)
            (after / "example.py").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "workspace_snapshot_mismatch"):
                verified_changes(
                    before, after, source_hash=source_hash, post_run_hash=post_run_hash
                )

    def test_protected_and_binary_changes_are_refused(self):
        for name, content, expected in (
            (".env", b"private", "workspace_changes_protected"),
            ("file.bin", b"\x00", "workspace_changes_binary"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                before, after = root / "before", root / "after"
                before.mkdir()
                after.mkdir()
                (after / name).write_bytes(content)
                with self.assertRaisesRegex(RunnerError, expected):
                    verified_changes(
                        before,
                        after,
                        source_hash=_hash_tree(before),
                        post_run_hash=_hash_tree(after),
                    )
