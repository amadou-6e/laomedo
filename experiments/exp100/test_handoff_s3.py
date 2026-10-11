"""Credential-free checks for the frozen EXP-100/S3 handoff candidate."""

from pathlib import Path
import hashlib
import os
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from experiments.exp100 import bundle_transfer as verifier_module
from experiments.exp100 import handoff_s3 as handoff_module
from experiments.exp100.handoff_s3 import HANDOFF_NAME, _plain_file, transfer
from experiments.exp100.probe_s3 import record_once


class HandoffS3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trusted = self.root / "trusted"
        self.trusted.mkdir()
        self.private = self.root / "private"
        self.private.mkdir()
        self.runner_state = self.root / "runner"
        self.run = self.runner_state / "runs" / "run-a"
        self.run.mkdir(parents=True)
        self.agent = self.run / "workspace"
        self.git("init", "-q", cwd=self.trusted)
        (self.trusted / "source.txt").write_text("baseline", encoding="utf-8")
        self.git("add", "source.txt", cwd=self.trusted)
        self.git("-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-qm", "baseline",
                 cwd=self.trusted)
        self.baseline = self.git("rev-parse", "HEAD", cwd=self.trusted)
        self.git("clone", "-q", "--no-local", str(self.trusted), str(self.agent),
                 cwd=self.root)
        self.git("checkout", "-qb", "run-a", cwd=self.agent)
        self.record = {"run_id": "run-a", "status": "completed",
                       "workspace_mode": "git", "git_baseline": self.baseline,
                       "github_scope": {"repository": "example/disposable",
                                        "branch": "run-a"}}

    def git(self, *args, cwd):
        completed = subprocess.run(["git", "-C", str(cwd), *args],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def commit_and_bundle(self, name, *, prerequisite=None):
        (self.agent / name).write_text(name, encoding="utf-8")
        self.git("add", name, cwd=self.agent)
        self.git("-c", "user.name=Agent", "-c",
                 "user.email=agent@example.invalid", "commit", "-qm", name,
                 cwd=self.agent)
        commit = self.git("rev-parse", "HEAD", cwd=self.agent)
        bundle = self.agent / HANDOFF_NAME
        bundle.unlink(missing_ok=True)
        args = ["bundle", "create", str(bundle), "refs/heads/run-a"]
        if prerequisite is not None:
            args.append("^" + prerequisite)
        self.git(*args, cwd=self.agent)
        return commit

    def test_bound_bundle_is_imported_into_private_stage(self):
        commit = self.commit_and_bundle("agent.txt")
        result = transfer(self.record, self.runner_state, self.private, self.trusted,
                          attempt_id="first")
        self.assertEqual(result["reason"], "accepted")
        self.assertEqual(result["commit"], commit)
        self.assertTrue((self.private / "run-a" / "first" / "frozen.bundle").is_file())
        self.assertEqual(self.git("cat-file", "-t", commit,
                                  cwd=Path(result["stage"])), "commit")
        moved_agent = self.agent.with_name("agent-no-longer-at-run-path")
        self.agent.rename(moved_agent)
        self.assertEqual(self.git("cat-file", "-t", commit,
                                  cwd=Path(result["stage"])), "commit")
        original_hash = result["bundle_sha256"]
        (moved_agent / HANDOFF_NAME).write_bytes(b"different bytes")
        with self.assertRaisesRegex(RuntimeError, "attempt_already_reserved"):
            transfer(self.record, self.runner_state, self.private, self.trusted,
                     attempt_id="first")
        self.assertEqual(__import__("json").loads(
            (self.private / "run-a" / "first" / "result.json").read_text())
                         ["bundle_sha256"], original_hash)

    def test_thin_bundle_requires_host_confirmed_stage(self):
        first_commit = self.commit_and_bundle("first.txt")
        first = transfer(self.record, self.runner_state, self.private, self.trusted,
                         attempt_id="first")
        self.assertEqual(first["reason"], "accepted")
        second_commit = self.commit_and_bundle("second.txt",
                                                prerequisite=first_commit)
        fresh_private = self.root / "fresh-private"
        fresh_private.mkdir()
        missing_seed = transfer(self.record, self.runner_state, fresh_private,
                                self.trusted, attempt_id="thin-without-seed")
        self.assertEqual(missing_seed["reason"], "missing_prerequisite")
        with self.assertRaisesRegex(RuntimeError, "confirmed_stage_required"):
            transfer(self.record, self.runner_state, self.private, self.trusted,
                     attempt_id="without-confirmed")
        accepted = transfer(self.record, self.runner_state, self.private, self.trusted,
                            attempt_id="with-confirmed",
                            confirmed_attempt_id=first["attempt_id"])
        self.assertEqual(accepted["reason"], "accepted")
        self.assertEqual(accepted["commit"], second_commit)

    def test_wrong_branch_and_run_are_refused(self):
        self.commit_and_bundle("agent.txt")
        wrong_run = {**self.record, "run_id": "other"}
        with self.assertRaisesRegex(RuntimeError, "run_binding_invalid"):
            transfer(wrong_run, self.runner_state, self.private, self.trusted,
                     attempt_id="wrong-run")
        wrong_branch = {**self.record, "github_scope": {"branch": "other"}}
        result = transfer(wrong_branch, self.runner_state, self.private, self.trusted,
                          attempt_id="wrong-branch")
        self.assertEqual(result["reason"], "ref_name")
        self.assertIsNone(result["stage"])

    def test_valid_bundle_from_another_run_cannot_bind_to_this_run(self):
        other_run = self.runner_state / "runs" / "run-b"
        other_run.mkdir()
        other_agent = other_run / "workspace"
        self.git("clone", "-q", "--no-local", str(self.trusted), str(other_agent),
                 cwd=self.root)
        self.git("checkout", "-qb", "run-b", cwd=other_agent)
        (other_agent / "b.txt").write_text("from B", encoding="utf-8")
        self.git("add", "b.txt", cwd=other_agent)
        self.git("-c", "user.name=Agent", "-c",
                 "user.email=agent@example.invalid", "commit", "-qm", "B",
                 cwd=other_agent)
        self.git("bundle", "create", str(other_agent / HANDOFF_NAME),
                 "refs/heads/run-b", cwd=other_agent)
        other = {**self.record, "run_id": "run-b",
                 "github_scope": {"branch": "run-b"}}
        accepted = transfer(other, self.runner_state, self.private, self.trusted,
                            attempt_id="other")
        self.assertEqual(accepted["reason"], "accepted")
        (self.agent / HANDOFF_NAME).write_bytes((other_agent / HANDOFF_NAME).read_bytes())
        rejected = transfer(self.record, self.runner_state, self.private,
                            self.trusted, attempt_id="wrong-run-bytes")
        self.assertEqual(rejected["reason"], "ref_name")
        self.assertIsNone(rejected["stage"])

    def test_wrong_baseline_truncated_and_malformed_leave_failure_records(self):
        self.commit_and_bundle("agent.txt")
        original = (self.agent / HANDOFF_NAME).read_bytes()
        (self.trusted / "later.txt").write_text("later", encoding="utf-8")
        self.git("add", "later.txt", cwd=self.trusted)
        self.git("-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-qm", "later",
                 cwd=self.trusted)
        later = self.git("rev-parse", "HEAD", cwd=self.trusted)
        wrong = {**self.record, "git_baseline": later}
        mismatch = transfer(wrong, self.runner_state, self.private, self.trusted,
                            attempt_id="wrong-baseline")
        self.assertEqual(mismatch["reason"], "baseline_ancestry")
        for attempt, payload in (("truncated", original[:-20]),
                                 ("malformed", b"not a git bundle")):
            (self.agent / HANDOFF_NAME).write_bytes(payload)
            result = transfer(self.record, self.runner_state, self.private,
                              self.trusted, attempt_id=attempt)
            self.assertNotEqual(result["reason"], "accepted")
            saved = self.private / "run-a" / attempt / "result.json"
            self.assertEqual(__import__("json").loads(saved.read_text())["reason"],
                             result["reason"])
            self.assertEqual(result["bundle_sha256"], hashlib.sha256(payload).hexdigest())

    def test_private_stage_must_be_disjoint_from_all_runner_mounts(self):
        self.commit_and_bundle("agent.txt")
        another_mount = self.runner_state / "runs" / "run-b" / "workspace"
        another_mount.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "private_stage_boundary_invalid"):
            transfer(self.record, self.runner_state, another_mount,
                     self.trusted, attempt_id="bad-placement")
        self.assertFalse((another_mount / "run-a" / "bad-placement").exists())

    def test_incomplete_prior_attempt_blocks_new_transfer(self):
        self.commit_and_bundle("agent.txt")
        (self.private / "run-a").mkdir()
        (self.private / "run-a" / "crashed-before-result").mkdir()
        with self.assertRaisesRegex(RuntimeError, "attempt_unreconciled"):
            transfer(self.record, self.runner_state, self.private, self.trusted,
                     attempt_id="second")
        self.assertFalse((self.private / "run-a" / "second").exists())

    def test_divergent_later_commit_is_not_accepted_as_fast_forward(self):
        self.commit_and_bundle("first.txt")
        first = transfer(self.record, self.runner_state, self.private, self.trusted,
                         attempt_id="first")
        self.assertEqual(first["reason"], "accepted")
        alternative = self.root / "alternate-agent"
        self.git("clone", "-q", "--no-local", str(self.trusted), str(alternative),
                 cwd=self.root)
        self.git("checkout", "-qb", "run-a", cwd=alternative)
        (alternative / "different.txt").write_text("different", encoding="utf-8")
        self.git("add", "different.txt", cwd=alternative)
        self.git("-c", "user.name=Agent", "-c",
                 "user.email=agent@example.invalid", "commit", "-qm", "different",
                 cwd=alternative)
        bundle = self.agent / HANDOFF_NAME
        bundle.unlink()
        self.git("bundle", "create", str(bundle), "refs/heads/run-a",
                 cwd=alternative)
        refused = transfer(self.record, self.runner_state, self.private,
                           self.trusted, attempt_id="divergent",
                           confirmed_attempt_id=first["attempt_id"])
        self.assertEqual(refused["reason"], "confirmed_ancestry_invalid")

    def test_windows_reparse_attribute_is_refused_even_for_regular_file(self):
        status = SimpleNamespace(st_mode=__import__("stat").S_IFREG | 0o600,
                                 st_nlink=1, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=status):
            self.assertFalse(_plain_file(self.agent / HANDOFF_NAME))

    def test_replacement_detected_after_open_is_not_staged(self):
        self.commit_and_bundle("agent.txt")
        with patch.object(handoff_module, "_plain_file",
                          side_effect=[True, False]):
            result = transfer(self.record, self.runner_state, self.private,
                              self.trusted, attempt_id="replaced")
        self.assertEqual(result["reason"], "handoff_replaced")
        self.assertIsNone(result["stage"])

    def test_hardlink_and_oversize_are_refused_before_git(self):
        bundle = self.agent / HANDOFF_NAME
        bundle.write_bytes(b"plain")
        linked = self.agent / "linked.bundle"
        linked.hardlink_to(bundle)
        refused = transfer(self.record, self.runner_state, self.private, self.trusted,
                           attempt_id="hardlink")
        self.assertEqual(refused["reason"], "handoff_not_regular")
        linked.unlink()
        with bundle.open("wb") as stream:
            stream.truncate(4 * 1024 * 1024 + 1)
        refused = transfer(self.record, self.runner_state, self.private, self.trusted,
                           attempt_id="oversize")
        self.assertEqual(refused["reason"], "handoff_size_or_type")

    def test_workflow_change_and_extra_ref_never_reach_stage(self):
        workflow = self.agent / ".github" / "workflows" / "probe.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: unsafe", encoding="utf-8")
        self.git("add", ".github/workflows/probe.yml", cwd=self.agent)
        self.git("-c", "user.name=Agent", "-c",
                 "user.email=agent@example.invalid", "commit", "-qm", "workflow",
                 cwd=self.agent)
        bundle = self.agent / HANDOFF_NAME
        self.git("bundle", "create", str(bundle), "refs/heads/run-a",
                 cwd=self.agent)
        refused = transfer(self.record, self.runner_state, self.private, self.trusted,
                           attempt_id="workflow")
        self.assertEqual(refused["reason"], "workflow_change")
        self.assertIsNone(refused["stage"])

        bundle.unlink()
        self.git("branch", "extra", cwd=self.agent)
        self.git("bundle", "create", str(bundle), "refs/heads/run-a",
                 "refs/heads/extra", cwd=self.agent)
        refused = transfer(self.record, self.runner_state, self.private, self.trusted,
                           attempt_id="extra-ref")
        self.assertEqual(refused["reason"], "ref_count")
        self.assertIsNone(refused["stage"])

    def test_agent_hook_and_hostile_remote_are_not_used(self):
        marker = self.root / "unwanted-hook-fired"
        hook = self.agent / ".git" / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\nprintf FIRED > '" +
                        str(marker).replace("'", "") + "'\n", encoding="utf-8")
        hook.chmod(0o755)
        self.git("remote", "add", "hostile", "https://invalid.example/steal",
                 cwd=self.agent)
        self.commit_and_bundle("agent.txt")
        result = transfer(self.record, self.runner_state, self.private, self.trusted,
                          attempt_id="hostile")
        self.assertEqual(result["reason"], "accepted")
        self.assertFalse(marker.exists())

    def test_host_git_guard_rejects_agent_repository_and_local_git_still_works(self):
        self.commit_and_bundle("agent.txt")
        self.assertIn(HANDOFF_NAME, self.git("status", "--short", cwd=self.agent))
        alternate = self.agent / ".git" / "objects" / "info" / "alternates"
        alternate.write_text(str(self.root / "hostile-objects"), encoding="utf-8")
        original = verifier_module.git

        def guarded(args, *, directory=None, env=None):
            if directory is not None and Path(directory).resolve() == self.agent.resolve():
                raise AssertionError("host Git entered agent repository")
            if "-C" in args and str(self.agent) in args:
                raise AssertionError("host Git entered agent repository")
            return original(args, directory=directory, env=env)

        with patch.object(verifier_module, "git", side_effect=guarded), \
                patch.object(handoff_module, "git", side_effect=guarded):
            with self.assertRaisesRegex(AssertionError, "host Git entered"):
                guarded(["-C", str(self.agent), "status"])
            result = transfer(self.record, self.runner_state, self.private,
                              self.trusted, attempt_id="git-guard")
        self.assertEqual(result["reason"], "accepted")

    def test_symlink_handoff_is_refused_where_supported(self):
        destination = self.agent / "other.bundle"
        destination.write_bytes(b"untrusted")
        try:
            (self.agent / HANDOFF_NAME).symlink_to(destination)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        refused = transfer(self.record, self.runner_state, self.private, self.trusted,
                           attempt_id="symlink")
        self.assertEqual(refused["reason"], "handoff_not_regular")

    @unittest.skipUnless(os.name == "nt", "Windows junction control")
    def test_windows_junction_handoff_is_refused(self):
        target = self.root / "junction-target"
        target.mkdir()
        link = self.agent / HANDOFF_NAME
        created = subprocess.run(["cmd.exe", "/c", "mklink", "/J",
                                  str(link), str(target)], capture_output=True,
                                 text=True, timeout=10)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertTrue(link.lstat().st_file_attributes & 0x400)
        refused = transfer(self.record, self.runner_state, self.private,
                           self.trusted, attempt_id="junction")
        self.assertEqual(refused["reason"], "handoff_not_regular")


class ProbeReservationTests(unittest.TestCase):
    def test_failed_first_record_consumes_identity(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "observation-s3.json"
            result = record_once(output, "a" * 40, lambda: {
                "identity": "EXP-100-S3-01", "status": "failed",
                "cases": [{"case": "control", "status": "failed"}]})
            self.assertEqual(result["status"], "failed")
            self.assertEqual(__import__("json").loads(output.read_text())["cases"],
                             [{"case": "control", "status": "failed"}])
            with self.assertRaises(FileExistsError):
                record_once(output, "a" * 40, lambda: {"status": "passed"})

    def test_unexpected_error_still_records_failure_without_private_text(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "observation-s3.json"
            def fail():
                raise RuntimeError("private path that must not be recorded")
            result = record_once(output, "b" * 40, fail)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error_class"], "RuntimeError")
            self.assertNotIn("private path", output.read_text())


if __name__ == "__main__":
    unittest.main()
