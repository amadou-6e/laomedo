"""Trusted run-binding and one-shot freeze checks; no GitHub or Docker."""

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from laomedo.bundle_ingest import (BundleIngestError, HANDOFF_NAME,
                                   MAX_BUNDLE_BYTES, freeze_run_bundle)


class BundleIngestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runner = self.root / "runner-state"
        self.private = self.root / "private-stage"
        self.run_dir = self.runner / "runs" / "run-a"
        self.workspace = self.run_dir / "workspace"
        self.workspace.mkdir(parents=True)
        self.private.mkdir()
        self.record = {"run_id": "run-a", "status": "completed",
                       "workspace_mode": "git", "git_baseline": "a" * 40,
                       "github_scope": {"repository": "example/disposable",
                                        "branch": "run-branch"}}
        self._save_record()
        self.bundle = self.workspace / HANDOFF_NAME
        self.bundle.write_bytes(b"synthetic bundle bytes")

    def _save_record(self):
        (self.run_dir / "record.json").write_text(
            json.dumps(self.record), encoding="utf-8")

    def _freeze(self, attempt="attempt-1"):
        return freeze_run_bundle(self.runner, self.private,
                                 run_id="run-a", attempt_id=attempt)

    def test_freezes_only_fixed_run_file_with_hash_and_reserved_result(self):
        self.record["agent_selected_path"] = str(self.root / "wrong.bundle")
        self._save_record()
        result = self._freeze()
        self.assertEqual(result["status"], "frozen")
        self.assertEqual(result["repository"], "example/disposable")
        self.assertEqual(result["branch"], "run-branch")
        self.assertEqual(result["baseline"], "a" * 40)
        self.assertEqual(result["run_record_sha256"], hashlib.sha256(
            (self.run_dir / "record.json").read_bytes()).hexdigest())
        self.assertEqual(result["bundle_sha256"], hashlib.sha256(
            b"synthetic bundle bytes").hexdigest())
        frozen = self.private / "run-a" / "attempt-1" / "input.bundle"
        self.assertEqual(frozen.read_bytes(), b"synthetic bundle bytes")
        self.bundle.write_bytes(b"changed after freeze")
        self.assertEqual(frozen.read_bytes(), b"synthetic bundle bytes")
        saved = json.loads((frozen.parent / "result.json").read_text())
        self.assertEqual(saved, result)
        self.assertFalse((self.private / "run-a.lock").exists())

    def test_same_attempt_never_overwrites_frozen_bytes(self):
        self._freeze()
        with self.assertRaisesRegex(BundleIngestError, "attempt_already_reserved"):
            self._freeze()
        self.assertEqual((self.private / "run-a" / "attempt-1" /
                          "input.bundle").read_bytes(), b"synthetic bundle bytes")

    def test_stale_lock_blocks_new_attempt(self):
        (self.private / "run-a.lock").write_text("unknown attempt\n")
        with self.assertRaisesRegex(BundleIngestError,
                                    "run_transfer_busy_or_unreconciled"):
            self._freeze("attempt-2")

    def test_unknown_prior_attempt_blocks_fresh_identity(self):
        with patch("laomedo.bundle_ingest._bundle_bytes",
                   side_effect=RuntimeError("unreported disk failure")):
            with self.assertRaises(RuntimeError):
                self._freeze()
        saved = json.loads((self.private / "run-a" / "attempt-1" /
                            "result.json").read_text())
        self.assertEqual(saved["status"], "unknown")
        self.assertFalse((self.private / "run-a.lock").exists())
        with self.assertRaisesRegex(BundleIngestError, "attempt_unreconciled"):
            self._freeze("attempt-2")

    def test_frozen_prior_attempt_blocks_fresh_identity(self):
        self._freeze()
        with self.assertRaisesRegex(BundleIngestError, "attempt_unreconciled"):
            self._freeze("attempt-2")

    def test_oversized_bundle_is_refused_with_consumed_attempt(self):
        self.bundle.write_bytes(b"x" * (MAX_BUNDLE_BYTES + 1))
        result = self._freeze()
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["reason"], "bundle_size_or_type")
        self.assertFalse((self.private / "run-a" / "attempt-1" /
                          "input.bundle").exists())
        with self.assertRaisesRegex(BundleIngestError, "attempt_already_reserved"):
            self._freeze()

    def test_bundle_symlink_is_refused(self):
        other = self.root / "other.bundle"
        other.write_bytes(b"outside")
        self.bundle.unlink()
        try:
            self.bundle.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("host does not permit file symlinks")
        result = self._freeze()
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["reason"], "bundle_not_regular")

    def test_hardlinked_bundle_is_refused(self):
        other = self.root / "same-inode.bundle"
        try:
            os.link(self.bundle, other)
        except (OSError, NotImplementedError):
            self.skipTest("host does not permit hardlinks")
        result = self._freeze()
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["reason"], "bundle_size_or_type")

    def test_reparse_attribute_is_refused_without_real_junction_rights(self):
        marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", None)
        if marker is None:
            self.skipTest("OS has no reparse attribute")
        real_lstat = Path.lstat

        class ReparseStatus:
            def __init__(self, original):
                self.original = original
                self.st_mode = original.st_mode
                self.st_file_attributes = marker

            def __getattr__(self, name):
                return getattr(self.original, name)

        def synthetic_lstat(path):
            original = real_lstat(path)
            return ReparseStatus(original) if path == self.bundle else original

        with patch.object(Path, "lstat", synthetic_lstat):
            result = self._freeze()
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["reason"], "bundle_not_regular")

    def test_workspace_redirect_and_run_mismatch_refuse_before_attempt(self):
        self.record["run_id"] = "run-b"
        self._save_record()
        with self.assertRaisesRegex(BundleIngestError, "run_binding_invalid"):
            self._freeze()
        self.record["run_id"] = "run-a"
        self._save_record()
        self.workspace.rename(self.run_dir / "real-workspace")
        try:
            self.workspace.symlink_to(self.run_dir / "real-workspace",
                                      target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("host does not permit directory symlinks")
        with self.assertRaisesRegex(BundleIngestError, "run_binding_invalid"):
            self._freeze()

    def test_unbounded_saved_run_record_is_refused(self):
        (self.run_dir / "record.json").write_bytes(b"x" * (256 * 1024 + 1))
        with self.assertRaisesRegex(BundleIngestError, "run_binding_invalid"):
            self._freeze()

    def test_private_stage_cannot_be_inside_runner_or_git_checkout(self):
        inside_runner = self.runner / "private-stage"
        inside_runner.mkdir()
        with self.assertRaisesRegex(BundleIngestError, "stage_boundary_invalid"):
            freeze_run_bundle(self.runner, inside_runner,
                              run_id="run-a", attempt_id="attempt-1")
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(BundleIngestError, "stage_boundary_invalid"):
            self._freeze()


if __name__ == "__main__":
    unittest.main()
