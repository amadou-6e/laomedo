"""Unexecuted live-controller preflight controls; no HTTP request or process."""
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from experiments.exp104 import native_managed_probe as probe


class NativeManagedProbeTests(unittest.TestCase):
    def test_exec_trusts_only_fixture_mount_including_helper_children(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-managed-command-test-") as directory:
            root = Path(directory)
            (root / "deadline").write_text("100")
            (root / "a-ready.json").write_text(json.dumps({"container_id": "owned-id"}))
            selected = probe.identities("a")
            for arguments in (["git", "fetch", "origin"], ["git", "push", "origin", "HEAD"],
                              ["gh", "pr", "view", "1"]):
                with self.subTest(arguments=arguments), \
                        patch.object(probe.time, "monotonic", return_value=1), \
                        patch.object(probe, "inspect_exact", return_value=("owned", "owned-id")), \
                        patch.object(probe.subprocess, "run",
                                     return_value=SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")) as run:
                    self.assertEqual(probe.agent_command(root, "a", arguments, "token", "capability"), "ok")
                    self.assertEqual(run.call_args.args[0], [
                        "docker", "exec", "-i", "--workdir=/draft",
                        "--env=GIT_CONFIG_COUNT=1", "--env=GIT_CONFIG_KEY_0=safe.directory",
                        "--env=GIT_CONFIG_VALUE_0=/draft", selected["name"], *arguments])

    def test_changed_target_stops_before_branch_reads(self):
        with patch.object(probe, "api", side_effect=[{"id": 999}, {}, {}]) as api:
            with self.assertRaisesRegex(ValueError, "preflight_target_mismatch"):
                probe.preflight("synthetic-secret")
            assert api.call_count == 3


    def test_existing_fresh_branch_is_refused_without_write(self):
        with patch.object(probe, "api", side_effect=[
                {"id": 1408647759, "default_branch": "main", "permissions": {"push": True}},
                {"object": {"sha": probe.BASELINE}}, {"login": "ga84jog"}, {}]) as api:
            with self.assertRaisesRegex(ValueError, "preflight_branch_exists"):
                probe.preflight("synthetic-secret")
            assert api.call_count == 4
