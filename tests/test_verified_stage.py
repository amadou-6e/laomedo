"""Credential-free local checks for a grant-bound verified bundle snapshot."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from laomedo.bundle_ingest import HANDOFF_NAME, freeze_run_bundle
from laomedo.bundle_stage import PINNED_IMAGE_ID
from laomedo.verified_stage import VerifiedStageError, resolve_verified_stage


class VerifiedStageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "--quiet")
        (self.repo / "base").write_text("base", encoding="ascii")
        self.git("add", "base")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                 "commit", "--quiet", "-m", "base")
        self.baseline = self.git("rev-parse", "HEAD")
        (self.repo / "change").write_text("change", encoding="ascii")
        self.git("add", "change")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                 "commit", "--quiet", "-m", "change")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("branch", "run-branch", self.commit)
        self.git("branch", "validated", self.commit)
        self.runner = self.root / "runner"
        self.private = self.root / "private"
        self.workspace = self.runner / "runs" / "run-a" / "workspace"
        self.workspace.mkdir(parents=True)
        self.private.mkdir()
        self.record = self.workspace.parent / "record.json"
        self.record.write_text(json.dumps({
            "run_id": "run-a", "status": "completed", "workspace_mode": "git",
            "git_baseline": self.baseline,
            "github_scope": {"repository": "example/disposable",
                             "branch": "run-branch"}}), encoding="utf-8")
        self.git("bundle", "create", str(self.workspace / HANDOFF_NAME),
                 "refs/heads/run-branch")
        frozen = freeze_run_bundle(self.runner, self.private, run_id="run-a",
                                   attempt_id="attempt-1")
        self.assertEqual(frozen["status"], "frozen")
        self.attempt = self.private / "run-a" / "attempt-1"
        self.verified = self.attempt / "verified.bundle"
        self.git("bundle", "create", str(self.verified), "refs/heads/validated")
        self.verification = self.attempt / "verification.json"
        self.verification.write_text(json.dumps({
            "run_id": "run-a", "attempt_id": "attempt-1",
            "status": "verified", "source_bundle_sha256": frozen["bundle_sha256"],
            "baseline": self.baseline, "commit": self.commit,
            "image_id": PINNED_IMAGE_ID,
            "baseline_bundle_sha256": "a" * 64,
            "policy_approved": False,
            "container": {"status": "verified", "cleanup_verified": True,
                          "success_marker_seen": True, "limits_verified": True,
                          "export_class": "ok",
                          "output_sha256": hashlib.sha256(
                              self.verified.read_bytes()).hexdigest(),
                          "output_bytes": self.verified.stat().st_size}}),
            encoding="utf-8")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True).stdout.decode().strip()

    def resolve(self, **overrides):
        scope = {"run_id": "run-a", "repository": "example/disposable",
                 "branch": "run-branch", "commit": self.commit,
                 "stage_attempt_id": "attempt-1"}
        scope.update(overrides)
        return resolve_verified_stage(self.runner, self.private, **scope)

    def test_verified_snapshot_is_immutable_and_pathless(self):
        stage = self.resolve()
        original = stage.bundle
        self.verified.write_bytes(b"tampered")
        self.assertEqual(stage.bundle, original)
        self.assertEqual(stage.bundle_sha256, hashlib.sha256(original).hexdigest())
        self.assertNotIn(str(self.private), repr(stage))
        self.assertNotIn(repr(original), repr(stage))
        with self.assertRaises(VerifiedStageError):
            self.resolve()

    def test_wrong_grant_scope_or_commit_refuses(self):
        for scope in ({"run_id": "run-b"}, {"repository": "other/disposable"},
                      {"branch": "other"}, {"commit": "0" * 40},
                      {"stage_attempt_id": "other"}):
            with self.subTest(scope=scope), self.assertRaises(VerifiedStageError):
                self.resolve(**scope)

    def test_changed_record_or_frozen_source_refuses(self):
        original = self.record.read_bytes()
        self.record.write_bytes(original + b" ")
        with self.assertRaises(VerifiedStageError):
            self.resolve()
        self.record.write_bytes(original)
        (self.attempt / "input.bundle").write_bytes(b"tampered")
        with self.assertRaises(VerifiedStageError):
            self.resolve()

    def test_unverified_or_unclean_attempt_refuses(self):
        for section, key, value in (("top", "status", "unknown"),
                                    ("top", "run_id", "run-b"),
                                    ("top", "attempt_id", "attempt-2"),
                                    ("top", "policy_approved", True),
                                    ("top", "image_id", "sha256:" + "0" * 64),
                                    ("top", "baseline_bundle_sha256", "bad"),
                                    ("container", "cleanup_verified", False),
                                    ("container", "success_marker_seen", False),
                                    ("container", "limits_verified", False),
                                    ("container", "export_class", "failed"),
                                    ("container", "output_bytes", 0),
                                    ("container", "output_sha256", "0" * 64),
                                    ("top", "source_bundle_sha256", "0" * 64)):
            original = self.verification.read_bytes()
            record = json.loads(original)
            target = record if section == "top" else record["container"]
            target[key] = value
            self.verification.write_text(json.dumps(record), encoding="utf-8")
            with self.subTest(key=key), self.assertRaises(VerifiedStageError):
                self.resolve()
            self.verification.write_bytes(original)

    def test_linked_or_oversized_output_refuses(self):
        linked = self.root / "linked.bundle"
        os.link(self.verified, linked)
        with self.assertRaises(VerifiedStageError):
            self.resolve()
        linked.unlink()
        self.verified.write_bytes(b"x" * (32 * 1024 * 1024 + 1))
        with self.assertRaises(VerifiedStageError):
            self.resolve()

    def test_symlinked_stage_files_refuse(self):
        for target in (self.verification, self.verified):
            original = target.read_bytes()
            other = self.root / "other-file"
            other.write_bytes(original)
            target.unlink()
            try:
                target.symlink_to(other)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            with self.assertRaises(VerifiedStageError):
                self.resolve()
            target.unlink()
            target.write_bytes(original)
            other.unlink()

    def test_real_second_run_cannot_be_reached_by_first_run_scope(self):
        other = self.runner / "runs" / "run-b"
        (other / "workspace").mkdir(parents=True)
        record = json.loads(self.record.read_text())
        record["run_id"] = "run-b"
        (other / "record.json").write_text(json.dumps(record))
        second_home = self.private / "run-b" / "exclusive-b"
        second_home.mkdir(parents=True)
        frozen = json.loads((self.attempt / "result.json").read_text())
        frozen["run_id"] = "run-b"
        frozen["attempt_id"] = "exclusive-b"
        frozen["run_record_sha256"] = hashlib.sha256(
            (other / "record.json").read_bytes()).hexdigest()
        (second_home / "result.json").write_text(json.dumps(frozen))
        (second_home / "input.bundle").write_bytes(
            (self.attempt / "input.bundle").read_bytes())
        (second_home / "verified.bundle").write_bytes(self.verified.read_bytes())
        verification = json.loads(self.verification.read_text())
        verification.update(run_id="run-b", attempt_id="exclusive-b")
        (second_home / "verification.json").write_text(json.dumps(verification))
        other_stage = self.resolve(run_id="run-b", stage_attempt_id="exclusive-b")
        self.assertEqual(other_stage.run_id, "run-b")
        # The first run grant cannot reach the other run's unique attempt.
        with self.assertRaises(VerifiedStageError):
            self.resolve(stage_attempt_id="exclusive-b")

    def test_distinct_attempt_changes_stage_digest(self):
        first = self.resolve()
        second_attempt = self.private / "run-a" / "attempt-2"
        second_attempt.mkdir()
        frozen = json.loads((self.attempt / "result.json").read_text())
        frozen["attempt_id"] = "attempt-2"
        (second_attempt / "result.json").write_text(json.dumps(frozen))
        (second_attempt / "input.bundle").write_bytes(
            (self.attempt / "input.bundle").read_bytes())
        (second_attempt / "verified.bundle").write_bytes(self.verified.read_bytes())
        verification = json.loads(self.verification.read_text())
        verification["attempt_id"] = "attempt-2"
        (second_attempt / "verification.json").write_text(json.dumps(verification))
        second = self.resolve(stage_attempt_id="attempt-2")
        self.assertNotEqual(first.stage_digest, second.stage_digest)
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)
