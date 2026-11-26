"""Verified source-to-snapshot change projection."""

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.workspaces.changes import verified_changes
from laomedo.agents.workspaces.utils import _hash_tree


class VerifiedChangesTests(unittest.TestCase):
    def test_runner_projects_only_completed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after = root / "canonical", root / "post-run"
            before.mkdir()
            after.mkdir()
            (before / "code.py").write_text("old\n", encoding="utf-8")
            (after / "code.py").write_text("new\n", encoding="utf-8")
            record = {
                "run_id": "run",
                "status": "completed",
                "snapshot_ready": True,
                "source_hash": _hash_tree(before),
                "post_run_hash": _hash_tree(after),
                "imported_artifacts": [],
            }
            runner = SimpleNamespace(status=lambda _: record, _run_dir=lambda _: root)
            changes = BaseAgent.workspace_changes(runner, "run")
            self.assertIn("+new", changes.patch)
            self.assertTrue(changes.patch_hash.startswith("sha256:"))
            self.assertNotIn("patch", changes.model_dump())
            (after / "code.py").write_text("old\n", encoding="utf-8")
            record["post_run_hash"] = _hash_tree(after)
            with self.assertRaisesRegex(RunnerError, "workspace_changes_empty"):
                BaseAgent.workspace_changes(runner, "run")
            record["status"] = "running"
            with self.assertRaisesRegex(
                RunnerError, "workspace_changes_run_incomplete"
            ):
                BaseAgent.workspace_changes(runner, "run")

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
                before,
                after,
                source_hash=source_hash,
                post_run_hash=post_run_hash,
                imported_artifacts=[],
            )
            self.assertIn("-value = 1", patch)
            self.assertIn("+value = 2", patch)
            (after / "example.py").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "workspace_snapshot_mismatch"):
                verified_changes(
                    before,
                    after,
                    source_hash=source_hash,
                    post_run_hash=post_run_hash,
                    imported_artifacts=[],
                )

    def test_protected_and_binary_changes_are_refused(self):
        for name, content, expected in (
            (".env", b"private", "workspace_changes_protected"),
            ("secrets.json", b"private", "workspace_changes_protected"),
            ("readme\u202etxt", b"changed", "workspace_changes_protected"),
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
                        imported_artifacts=[],
                    )

    def test_no_newline_and_directory_or_imported_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (before / "a.txt").write_bytes(b"before")
            (after / "a.txt").write_bytes(b"after")
            (after / "b.txt").write_text("second\n", encoding="utf-8")
            kwargs = {
                "source_hash": _hash_tree(before),
                "post_run_hash": _hash_tree(after),
                "imported_artifacts": [],
            }
            patch = verified_changes(before, after, **kwargs)
            self.assertIn("+after\n\\ No newline at end of file\nFile: b.txt", patch)
            with self.assertRaisesRegex(
                RunnerError, "workspace_changes_imports_unsupported"
            ):
                verified_changes(
                    before, after, **{**kwargs, "imported_artifacts": [{}]}
                )
            (after / "new-directory").mkdir()
            kwargs["post_run_hash"] = _hash_tree(after)
            with self.assertRaisesRegex(
                RunnerError, "workspace_changes_directories_unsupported"
            ):
                verified_changes(before, after, **kwargs)

    def test_unicode_and_control_separators_do_not_split_diff_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (before / "a.txt").write_bytes("old\u2028one\rpart\fend\n".encode())
            (after / "a.txt").write_bytes("new\u2028one\rpart\fend\n".encode())
            patch = verified_changes(
                before,
                after,
                source_hash=_hash_tree(before),
                post_run_hash=_hash_tree(after),
                imported_artifacts=[],
            )
            self.assertIn("+new\u2028one\rpart\fend\n", patch)
            self.assertNotIn("No newline at end of file", patch)
