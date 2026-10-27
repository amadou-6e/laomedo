"""Credential-free control for agent-owned Git config reaching host helpers."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from laomedo.host.mediation.agent_cli import configure_remote
from laomedo.agents.local_runner import _copy_tree, _hash_tree


@unittest.skipUnless(shutil.which("git"), "Git required")
class HostGitTests(unittest.TestCase):
    def test_host_helpers_do_not_execute_poisoned_git_configuration(self):
        with tempfile.TemporaryDirectory(prefix="exp139-host-config-") as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            def git(*args):
                return subprocess.run(["git", "-C", str(workspace), *args],
                    capture_output=True, timeout=15, check=True)
            git("init", "--template=")
            (workspace / "report.txt").write_text("report")
            (workspace / ".gitattributes").write_text("report.txt filter=hostile diff=hostile\n")
            (workspace / ".git/info").mkdir(exist_ok=True)
            (workspace / ".git/info/exclude").write_text("/.agents/skills/\n")
            marker = root / "host-execution-marker"
            hook = root / "hook.sh"
            hook.write_text('#!/bin/sh\nprintf EXECUTED > "' + marker.as_posix() + '"\nexit 0\n', newline="\n")
            hook.chmod(0o755)
            for key, value in (("core.fsmonitor", hook.as_posix()),
                               ("core.hooksPath", root.as_posix()),
                               ("filter.hostile.clean", 'sh "' + hook.as_posix() + '"'),
                               ("filter.hostile.smudge", 'sh "' + hook.as_posix() + '"'),
                               ("diff.hostile.command", 'sh "' + hook.as_posix() + '"'),
                               ("credential.helper", '!sh "' + hook.as_posix() + '"')):
                git("config", "--local", key, value)
            # Positive control: an ordinary unsafe host status really executes
            # our fixture fsmonitor. The marker contains no credential.
            git("status", "--porcelain")
            self.assertTrue(marker.exists(), "attack fixture must execute")
            marker.unlink()
            configure_remote(workspace, "fixture/repository")
            _hash_tree(workspace, exclude_root_git=True)
            _copy_tree(workspace, root / "snapshot", exclude_root_git=True)
            self.assertFalse(marker.exists())
            self.assertFalse((root / "snapshot/.git").exists())
            self.assertEqual((root / "snapshot/report.txt").read_text(), "report")


if __name__ == "__main__":
    unittest.main()
