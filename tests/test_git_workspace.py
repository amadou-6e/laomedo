"""Credential-free, opt-in whole-repository workspace preparation."""

from laomedo.git.command import GitCommandRunner

from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo.agents.workspaces.workspace import AgentWorkspace
from laomedo.agents.workspaces.models import WorkspacePaths
from laomedo.agents.workspaces.errors import GitWorkspaceError


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
        self.baseline = (
            self._git(self.source, "rev-parse", "HEAD").stdout.decode().strip()
        )

    def _git(self, source, *args):
        result = subprocess.run(
            ["git", "-C", str(source), *args],
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_clean_clone_preserves_commit_without_remote_or_host_config(self):
        hostile_home = self.root / "host-home"
        hostile_home.mkdir()
        marker = self.root / "host-trace.log"
        (hostile_home / ".gitconfig").write_text(
            "[trace2]\n\tnormalTarget = " + marker.as_posix() + "\n", encoding="utf-8"
        )
        destination = self.root / "run" / "workspace"
        destination.parent.mkdir()
        with patch.dict(
            os.environ,
            {
                "HOME": str(hostile_home),
                "USERPROFILE": str(hostile_home),
                "XDG_CONFIG_HOME": str(hostile_home),
            },
        ):
            pinned = AgentWorkspace(
                WorkspacePaths(source=self.source, directory=destination)
            ).prepare_git()
        self.assertEqual(pinned, self.baseline)
        self.assertEqual(
            self._git(destination, "rev-parse", "HEAD").stdout.decode().strip(),
            self.baseline,
        )
        self.assertEqual(self._git(destination, "remote").stdout.strip(), b"")
        self.assertEqual((destination / "task.txt").read_bytes(), b"task\n")
        self.assertFalse(marker.exists())

    def test_dirty_source_and_existing_destination_fail_before_clone(self):
        destination = self.root / "workspace"
        (self.source / "untracked.txt").write_bytes(b"not pinned\n")
        with self.assertRaisesRegex(GitWorkspaceError, "source_not_clean"):
            AgentWorkspace(
                WorkspacePaths(source=self.source, directory=destination)
            ).prepare_git()
        self.assertFalse(destination.exists())
        (self.source / "untracked.txt").unlink()
        destination.mkdir()
        with self.assertRaisesRegex(GitWorkspaceError, "git_workspace_path_invalid"):
            AgentWorkspace(
                WorkspacePaths(source=self.source, directory=destination)
            ).prepare_git()

    def test_submodule_gitlink_is_refused(self):
        self._git(
            self.source,
            "update-index",
            "--add",
            "--cacheinfo",
            "160000," + self.baseline + ",nested",
        )
        self._git(self.source, "commit", "-qm", "gitlink")
        with self.assertRaisesRegex(GitWorkspaceError, "submodule_source_unsupported"):
            AgentWorkspace(
                WorkspacePaths(source=self.source, directory=self.root / "workspace")
            ).prepare_git()

    def test_indexed_symlink_is_refused(self):
        self._git(
            self.source,
            "update-index",
            "--add",
            "--cacheinfo",
            "120000," + self.baseline + ",link",
        )
        self._git(self.source, "commit", "-qm", "symlink")
        with self.assertRaisesRegex(GitWorkspaceError, "symlink_source_unsupported"):
            AgentWorkspace(
                WorkspacePaths(source=self.source, directory=self.root / "workspace")
            ).prepare_git()

    def test_partial_clone_is_removed_on_failure(self):
        destination = self.root / "workspace"
        original = GitCommandRunner.run

        def fail_after_clone(runner, command):
            if "clone" in command.arguments:
                (destination / "partial").write_text("unfinished", encoding="utf-8")
                return subprocess.CompletedProcess(
                    command.arguments, 1, b"", b"synthetic failure"
                )
            return original(runner, command)

        with patch.object(GitCommandRunner, "run", new=fail_after_clone):
            with self.assertRaisesRegex(GitWorkspaceError, "git_clone_failed"):
                AgentWorkspace(
                    WorkspacePaths(source=self.source, directory=destination)
                ).prepare_git()
        self.assertFalse(destination.exists())

    def test_racing_destination_is_not_removed(self):
        destination = self.root / "workspace"
        original = GitCommandRunner.run

        def claim_destination_after_status(runner, command):
            result = original(runner, command)
            if "status" in command.arguments:
                destination.mkdir()
                (destination / "foreign").write_text("keep", encoding="utf-8")
            return result

        with patch.object(GitCommandRunner, "run", new=claim_destination_after_status):
            with self.assertRaisesRegex(
                GitWorkspaceError, "git_workspace_path_invalid"
            ):
                AgentWorkspace(
                    WorkspacePaths(source=self.source, directory=destination)
                ).prepare_git()
        self.assertEqual((destination / "foreign").read_text(encoding="utf-8"), "keep")

    def test_fsmonitor_source_config_does_not_run(self):
        marker = self.root / "fsmonitor.txt"
        command = f'echo fired > "{marker}"'
        self._git(self.source, "config", "core.fsmonitor", command)
        AgentWorkspace(
            WorkspacePaths(source=self.source, directory=self.root / "workspace")
        ).prepare_git()
        self.assertFalse(marker.exists())

    def test_tracked_skill_path_is_refused(self):
        skills = self.source / ".agents" / "skills" / "example"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("tracked", encoding="utf-8")
        self._git(self.source, "add", ".agents/skills/example/SKILL.md")
        self._git(self.source, "commit", "-qm", "tracked skill")
        with self.assertRaisesRegex(
            GitWorkspaceError, "tracked_skill_path_unsupported"
        ):
            AgentWorkspace(
                WorkspacePaths(source=self.source, directory=self.root / "workspace")
            ).prepare_git()


if __name__ == "__main__":
    unittest.main()
