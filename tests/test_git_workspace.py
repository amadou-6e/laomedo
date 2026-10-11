"""Credential-free, opt-in whole-repository workspace preparation."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo import git_workspace
from laomedo.git_workspace import GitWorkspaceError, prepare_git_workspace


class GitWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self._git(self.source, "init", "-q")
        self._git(self.source, "config", "user.name", "Fixture")
        self._git(self.source, "config", "user.email", "fixture@example.invalid")
        (self.source / "task.txt").write_bytes(b"task\n")
        self._git(self.source, "add", "task.txt")
        self._git(self.source, "commit", "-qm", "baseline")
        self.baseline = self._git(self.source, "rev-parse", "HEAD").stdout.decode().strip()

    def _git(self, source, *args):
        result = subprocess.run(["git", "-C", str(source), *args],
                                capture_output=True, check=False, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_clean_clone_preserves_commit_without_remote_or_host_config(self):
        hostile_home = self.root / "host-home"
        hostile_home.mkdir()
        marker = self.root / "host-trace.log"
        (hostile_home / ".gitconfig").write_text(
            "[trace2]\n\tnormalTarget = " + marker.as_posix() + "\n",
            encoding="utf-8")
        destination = self.root / "run" / "workspace"
        destination.parent.mkdir()
        with patch.dict(os.environ, {"HOME": str(hostile_home),
                                     "USERPROFILE": str(hostile_home),
                                     "XDG_CONFIG_HOME": str(hostile_home)}):
            pinned = prepare_git_workspace(self.source, destination)
        self.assertEqual(pinned, self.baseline)
        self.assertEqual(self._git(destination, "rev-parse", "HEAD").stdout.decode().strip(),
                         self.baseline)
        self.assertEqual(self._git(destination, "remote").stdout.strip(), b"")
        self.assertEqual((destination / "task.txt").read_bytes(), b"task\n")
        self.assertFalse(marker.exists())

    def test_dirty_source_and_existing_destination_fail_before_clone(self):
        destination = self.root / "workspace"
        (self.source / "untracked.txt").write_bytes(b"not pinned\n")
        with self.assertRaisesRegex(GitWorkspaceError, "source_not_clean"):
            prepare_git_workspace(self.source, destination)
        self.assertFalse(destination.exists())
        (self.source / "untracked.txt").unlink()
        destination.mkdir()
        with self.assertRaisesRegex(GitWorkspaceError, "git_workspace_path_invalid"):
            prepare_git_workspace(self.source, destination)

    def test_submodule_gitlink_is_refused(self):
        self._git(self.source, "update-index", "--add", "--cacheinfo",
                  "160000," + self.baseline + ",nested")
        self._git(self.source, "commit", "-qm", "gitlink")
        with self.assertRaisesRegex(GitWorkspaceError, "submodule_source_unsupported"):
            prepare_git_workspace(self.source, self.root / "workspace")

    def test_indexed_symlink_is_refused(self):
        self._git(self.source, "update-index", "--add", "--cacheinfo",
                  "120000," + self.baseline + ",link")
        self._git(self.source, "commit", "-qm", "symlink")
        with self.assertRaisesRegex(GitWorkspaceError, "symlink_source_unsupported"):
            prepare_git_workspace(self.source, self.root / "workspace")

    def test_partial_clone_is_removed_on_failure(self):
        destination = self.root / "workspace"
        original = git_workspace._bounded_git

        def fail_after_clone(args, env):
            if "clone" in args:
                (destination / "partial").write_text("unfinished", encoding="utf-8")
                return subprocess.CompletedProcess(args, 1, b"", b"synthetic failure")
            return original(args, env)

        with patch.object(git_workspace, "_bounded_git", side_effect=fail_after_clone):
            with self.assertRaisesRegex(GitWorkspaceError, "git_clone_failed"):
                prepare_git_workspace(self.source, destination)
        self.assertFalse(destination.exists())

    def test_racing_destination_is_not_removed(self):
        destination = self.root / "workspace"
        original = git_workspace._bounded_git

        def claim_destination_after_status(args, env):
            result = original(args, env)
            if "status" in args:
                destination.mkdir()
                (destination / "foreign").write_text("keep", encoding="utf-8")
            return result

        with patch.object(git_workspace, "_bounded_git",
                          side_effect=claim_destination_after_status):
            with self.assertRaisesRegex(GitWorkspaceError, "git_workspace_path_invalid"):
                prepare_git_workspace(self.source, destination)
        self.assertEqual((destination / "foreign").read_text(encoding="utf-8"), "keep")

    def test_fsmonitor_source_config_does_not_run(self):
        marker = self.root / "fsmonitor.txt"
        command = f'echo fired > "{marker}"'
        self._git(self.source, "config", "core.fsmonitor", command)
        prepare_git_workspace(self.source, self.root / "workspace")
        self.assertFalse(marker.exists())

    def test_tracked_skill_path_is_refused(self):
        skills = self.source / ".agents" / "skills" / "example"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("tracked", encoding="utf-8")
        self._git(self.source, "add", ".agents/skills/example/SKILL.md")
        self._git(self.source, "commit", "-qm", "tracked skill")
        with self.assertRaisesRegex(GitWorkspaceError, "tracked_skill_path_unsupported"):
            prepare_git_workspace(self.source, self.root / "workspace")


if __name__ == "__main__":
    unittest.main()
