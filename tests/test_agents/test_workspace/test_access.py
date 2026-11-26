"""Workspace preparation fails closed when files cannot be read or copied."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from laomedo.agents.errors import RunnerError
from laomedo.agents.workspaces.models import WorkspacePaths
from laomedo.agents.workspaces.utils import _hash_tree
from laomedo.agents.workspaces.workspace import AgentWorkspace


class WorkspaceAccessTests(unittest.TestCase):
    def test_unreadable_directory_is_not_omitted_from_hash(self):
        with tempfile.TemporaryDirectory() as directory:

            def walk(path, *, followlinks, onerror):
                onerror(PermissionError("private path"))
                return iter(())

            with patch("laomedo.agents.workspaces.utils.os.walk", side_effect=walk):
                with self.assertRaises(PermissionError):
                    _hash_tree(Path(directory))

    def test_copy_failure_has_safe_domain_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            workspace = AgentWorkspace(
                WorkspacePaths(source=source, directory=root / "run")
            )
            failure = shutil.Error(
                [("private source", "private destination", "denied")]
            )
            with patch(
                "laomedo.agents.workspaces.workspace._copy_tree", side_effect=failure
            ):
                with self.assertRaisesRegex(RunnerError, "^workspace_access_failed$"):
                    workspace.prepare(root / "canonical", git=False)
