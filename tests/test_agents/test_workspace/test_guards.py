"""Native sandbox guards are prepared symmetrically without relaxing patch policy."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.agents.codex.settings import WORKSPACE_GUARD_DIRECTORIES
from laomedo.agents.errors import RunnerError
from laomedo.agents.workspaces.changes import verified_changes
from laomedo.agents.workspaces.models import WorkspacePaths
from laomedo.agents.workspaces.utils import _hash_tree
from laomedo.agents.workspaces.workspace import AgentWorkspace


class WorkspaceGuardTests(unittest.TestCase):
    def _prepare(
        self, root, *, git=False, existing=False, guards=WORKSPACE_GUARD_DIRECTORIES
    ):
        source, workspace, canonical = (
            root / name for name in ("source", "workspace", "canonical")
        )
        source.mkdir()
        (source / "example.py").write_bytes(b"value = 1\n")
        if existing:
            (source / ".codex").mkdir()
            (source / ".codex" / "config.toml").write_bytes(b"# fixture\n")
        if git:
            self._init_git(source)
        original = _hash_tree(source, exclude_root_git=git)
        prepared = AgentWorkspace(
            WorkspacePaths(source=source, directory=workspace)
        ).prepare(canonical, git=git, guard_directories=guards)
        self.assertEqual(_hash_tree(source, exclude_root_git=git), original)
        return source, workspace, canonical, prepared

    def _init_git(self, source):
        for args in (
            ("init", "-q"),
            ("add", "."),
            (
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "baseline",
            ),
        ):
            subprocess.run(
                ["git", "-C", str(source), *args],
                check=True,
                capture_output=True,
                timeout=10,
            )

    def test_both_preparation_modes_hash_prepared_guards_and_project_only_real_edit(
        self,
    ):
        for git in (False, True):
            with self.subTest(git=git), tempfile.TemporaryDirectory() as directory:
                source, workspace, canonical, prepared = self._prepare(
                    Path(directory), git=git
                )
                for name in WORKSPACE_GUARD_DIRECTORIES:
                    self.assertFalse((source / name).exists())
                    self.assertTrue((workspace / name).is_dir())
                    self.assertTrue((canonical / name).is_dir())
                self.assertEqual(prepared.source_hash, _hash_tree(canonical))
                self.assertEqual(
                    prepared.source_hash, _hash_tree(workspace, exclude_root_git=git)
                )
                if git:
                    status = subprocess.run(
                        ["git", "-C", str(workspace), "status", "--porcelain"],
                        check=True,
                        capture_output=True,
                        timeout=10,
                    )
                    self.assertEqual(status.stdout, b"")
                (workspace / "example.py").write_text("value = 2\n", encoding="utf-8")
                post_run = Path(directory) / "post-run"
                shutil.copytree(canonical, post_run)
                (post_run / "example.py").write_text("value = 2\n", encoding="utf-8")
                patch = verified_changes(
                    canonical,
                    post_run,
                    source_hash=prepared.source_hash,
                    post_run_hash=_hash_tree(post_run),
                    imported_artifacts=[],
                )
                self.assertIn("+value = 2", patch)
                self.assertNotIn(".aws", patch)
                self.assertNotIn(".codex", patch)

    def test_existing_guard_contents_are_preserved_in_both_modes(self):
        for git in (False, True):
            with self.subTest(git=git), tempfile.TemporaryDirectory() as directory:
                source, workspace, canonical, _ = self._prepare(
                    Path(directory), git=git, existing=True
                )
                for root in (source, workspace, canonical):
                    self.assertEqual(
                        (root / ".codex/config.toml").read_text(encoding="utf-8"),
                        "# fixture\n",
                    )

    def test_guard_file_edits_and_unrelated_directory_changes_remain_refused(self):
        for name, expected in (
            (".aws/credentials", "workspace_changes_protected"),
            (".codex/config.toml", "workspace_changes_protected"),
            ("extra-directory", "workspace_changes_directories_unsupported"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                _, _, canonical, prepared = self._prepare(Path(directory))
                post_run = Path(directory) / "post-run"
                shutil.copytree(canonical, post_run)
                if name == "extra-directory":
                    (post_run / name).mkdir()
                else:
                    (post_run / name).write_text("fixture only\n", encoding="utf-8")
                with self.assertRaisesRegex(RunnerError, expected):
                    verified_changes(
                        canonical,
                        post_run,
                        source_hash=prepared.source_hash,
                        post_run_hash=_hash_tree(post_run),
                        imported_artifacts=[],
                    )

    def test_guard_file_collision_is_refused_before_snapshot_acceptance(self):
        for git in (False, True):
            with self.subTest(git=git), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()
                (source / ".aws").write_text("fixture", encoding="utf-8")
                if git:
                    self._init_git(source)
                with self.assertRaisesRegex(RunnerError, "unsafe_workspace_entry"):
                    AgentWorkspace(
                        WorkspacePaths(source=source, directory=root / "workspace")
                    ).prepare(
                        root / "canonical",
                        git=git,
                        guard_directories=WORKSPACE_GUARD_DIRECTORIES,
                    )

    def test_guard_replacement_with_link_is_refused_by_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, workspace, _, _ = self._prepare(root)
            target = root / "outside"
            target.mkdir()
            guard = workspace / ".aws"
            guard.rmdir()
            if os.name == "nt":
                subprocess.run(
                    ["cmd.exe", "/c", "mklink", "/J", str(guard), str(target)],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
                self.addCleanup(lambda: guard.rmdir() if guard.exists() else None)
            else:
                guard.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(RunnerError, "unsafe_workspace_entry"):
                _hash_tree(workspace)
            with self.assertRaisesRegex(RunnerError, "unsafe_workspace_entry"):
                AgentWorkspace(
                    WorkspacePaths(source=workspace, directory=root / "next-workspace")
                ).prepare(
                    root / "next-canonical",
                    git=False,
                    guard_directories=WORKSPACE_GUARD_DIRECTORIES,
                )

    def test_guard_replacement_with_file_remains_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            _, workspace, canonical, prepared = self._prepare(Path(directory))
            (workspace / ".aws").rmdir()
            (workspace / ".aws").write_bytes(b"fixture")
            with self.assertRaisesRegex(
                RunnerError, "workspace_changes_directories_unsupported"
            ):
                verified_changes(
                    canonical,
                    workspace,
                    source_hash=prepared.source_hash,
                    post_run_hash=_hash_tree(workspace),
                    imported_artifacts=[],
                )

    def test_other_providers_have_no_guards_and_unprepared_snapshots_are_unchanged(
        self,
    ):
        self.assertEqual(BaseAgent.workspace_guard_directories, ())
        self.assertEqual(
            CodexAgent.workspace_guard_directories, WORKSPACE_GUARD_DIRECTORIES
        )
        with tempfile.TemporaryDirectory() as directory:
            source, workspace, canonical, prepared = self._prepare(
                Path(directory), guards=()
            )
            self.assertEqual(_hash_tree(source), prepared.source_hash)
            self.assertEqual(_hash_tree(workspace), prepared.source_hash)
            self.assertEqual(_hash_tree(canonical), prepared.source_hash)
            self.assertFalse((canonical / ".aws").exists())
