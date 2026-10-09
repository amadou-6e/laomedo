"""Credential-free checks for the frozen EXP-100/S3 handoff candidate."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from experiments.exp100.handoff_s3 import HANDOFF_NAME, transfer


class HandoffS3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trusted = self.root / "trusted"
        self.trusted.mkdir()
        self.private = self.root / "private"
        self.private.mkdir()
        self.run = self.root / "runs" / "run-a"
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
        result = transfer(self.record, self.root, self.private, self.trusted,
                          attempt_id="first")
        self.assertEqual(result["reason"], "accepted")
        self.assertEqual(result["commit"], commit)
        self.assertTrue((self.private / "run-a-first" / "frozen.bundle").is_file())
        self.assertEqual(self.git("cat-file", "-t", commit,
                                  cwd=Path(result["stage"])), "commit")
        self.agent.rename(self.agent.with_name("agent-no-longer-at-run-path"))
        self.assertEqual(self.git("cat-file", "-t", commit,
                                  cwd=Path(result["stage"])), "commit")
        with self.assertRaises(FileExistsError):
            transfer(self.record, self.root, self.private, self.trusted,
                     attempt_id="first")

    def test_thin_bundle_requires_host_confirmed_stage(self):
        first_commit = self.commit_and_bundle("first.txt")
        first = transfer(self.record, self.root, self.private, self.trusted,
                         attempt_id="first")
        self.assertEqual(first["reason"], "accepted")
        second_commit = self.commit_and_bundle("second.txt",
                                                prerequisite=first_commit)
        missing = transfer(self.record, self.root, self.private, self.trusted,
                           attempt_id="without-confirmed")
        self.assertEqual(missing["reason"], "missing_prerequisite")
        accepted = transfer(self.record, self.root, self.private, self.trusted,
                            attempt_id="with-confirmed", confirmed=first)
        self.assertEqual(accepted["reason"], "accepted")
        self.assertEqual(accepted["commit"], second_commit)

    def test_wrong_branch_and_run_are_refused(self):
        self.commit_and_bundle("agent.txt")
        wrong_run = {**self.record, "run_id": "other"}
        with self.assertRaisesRegex(RuntimeError, "run_binding_invalid"):
            transfer(wrong_run, self.root, self.private, self.trusted,
                     attempt_id="wrong-run")
        wrong_branch = {**self.record, "github_scope": {"branch": "other"}}
        result = transfer(wrong_branch, self.root, self.private, self.trusted,
                          attempt_id="wrong-branch")
        self.assertEqual(result["reason"], "ref_name")
        self.assertIsNone(result["stage"])

    def test_hardlink_and_oversize_are_refused_before_git(self):
        bundle = self.agent / HANDOFF_NAME
        bundle.write_bytes(b"plain")
        linked = self.agent / "linked.bundle"
        linked.hardlink_to(bundle)
        refused = transfer(self.record, self.root, self.private, self.trusted,
                           attempt_id="hardlink")
        self.assertEqual(refused["reason"], "handoff_not_regular")
        linked.unlink()
        with bundle.open("wb") as stream:
            stream.truncate(4 * 1024 * 1024 + 1)
        refused = transfer(self.record, self.root, self.private, self.trusted,
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
        refused = transfer(self.record, self.root, self.private, self.trusted,
                           attempt_id="workflow")
        self.assertEqual(refused["reason"], "workflow_change")
        self.assertIsNone(refused["stage"])

        bundle.unlink()
        self.git("branch", "extra", cwd=self.agent)
        self.git("bundle", "create", str(bundle), "refs/heads/run-a",
                 "refs/heads/extra", cwd=self.agent)
        refused = transfer(self.record, self.root, self.private, self.trusted,
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
        result = transfer(self.record, self.root, self.private, self.trusted,
                          attempt_id="hostile")
        self.assertEqual(result["reason"], "accepted")
        self.assertFalse(marker.exists())

    def test_symlink_handoff_is_refused_where_supported(self):
        destination = self.agent / "other.bundle"
        destination.write_bytes(b"untrusted")
        try:
            (self.agent / HANDOFF_NAME).symlink_to(destination)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        refused = transfer(self.record, self.root, self.private, self.trusted,
                           attempt_id="symlink")
        self.assertEqual(refused["reason"], "handoff_not_regular")


if __name__ == "__main__":
    unittest.main()
