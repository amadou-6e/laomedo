"""No-Docker checks for the single-use S4 resource probe."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp100 import probe_s4


class ProbeS4Tests(unittest.TestCase):
    def test_failed_result_consumes_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation-s4.json"
            with patch.object(probe_s4, "run", return_value={
                    "identity": probe_s4.IDENTITY, "status": "failed"}):
                result = probe_s4.record_once(target, "a" * 40)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(json.loads(target.read_text())["status"], "failed")
                with self.assertRaises(FileExistsError):
                    probe_s4.record_once(target, "a" * 40)

    def test_unexpected_error_keeps_sanitized_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation-s4.json"
            with patch.object(probe_s4, "run", side_effect=RuntimeError("private path")):
                result = probe_s4.record_once(target, "b" * 40)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error_class"], "RuntimeError")
            self.assertNotIn("private path", target.read_text())

    def test_docker_config_is_inspected_and_exact_container_removed(self):
        inspected = {"Image": probe_s4.IMAGE_ID,
                     "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True,
                                    "Memory": probe_s4.MEMORY_BYTES,
                                    "PidsLimit": 32,
                                    "Tmpfs": {"/stage": "rw,size=32m"},
                                    "CapDrop": ["ALL"],
                                    "SecurityOpt": ["no-new-privileges:true"]},
                     "State": {"ExitCode": 0},
                     "Config": {"Labels": {"laomedo.experiment": "s4"},
                                "User": "10001:10001"},
                     "Mounts": [{"Type": "bind", "RW": False,
                                 "Destination": "/trusted"},
                                {"Type": "bind", "RW": False,
                                 "Destination": "/input.bundle"},
                                {"Type": "bind", "RW": False,
                                 "Destination": "/verify.sh"},
                                {"Type": "tmpfs", "RW": True}]}
        calls = []
        inspect_count = 0

        def fake_run(args, **_kwargs):
            nonlocal inspect_count
            calls.append(args)
            if args[1] == "inspect":
                inspect_count += 1
                return subprocess.CompletedProcess(args, 1 if inspect_count == 4 else 0,
                                                   json.dumps([inspected]), "")
            if args[1] == "start":
                return subprocess.CompletedProcess(args, 0,
                    "S4_GIT_VERSION=git version fixture\nS4_VERIFIED\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(probe_s4.secrets, "token_hex", return_value="abc"), \
                patch.object(probe_s4, "_run", side_effect=fake_run):
            result = probe_s4._docker_case(
                "valid_import", ["sh", "/verify.sh", "a" * 40, "b" * 40],
                [Path("C:/temp/trusted"), Path("C:/temp/input.bundle")])
        command = calls[0]
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["cleanup_verified"])
        self.assertEqual(result["marker"], "S4_VERIFIED")
        self.assertEqual(result["container_git_version"], "git version fixture")
        for option in ("--network", "none", "--read-only", "--memory", "128m",
                       "--pids-limit", "32", probe_s4.IMAGE_ID):
            self.assertIn(option, command)
        self.assertEqual(calls[-2], ["docker", "rm", "--force", "laomedo-s4-abc"])

    def test_disk_control_keeps_error_out_of_full_tmpfs(self):
        source = Path(probe_s4.__file__).read_text(encoding="utf-8")
        self.assertIn("if output=$(dd if=/dev/zero", source)
        self.assertNotIn("2>/stage/dd.err", source)

    def test_malformed_cleanup_inspection_is_not_accepted(self):
        calls = []

        def fake_run(args, **_kwargs):
            calls.append(args)
            if args[1] == "create":
                return subprocess.CompletedProcess(args, 1, "", "")
            return subprocess.CompletedProcess(args, 0, "malformed", "")

        with patch.object(probe_s4.secrets, "token_hex", return_value="abc"), \
                patch.object(probe_s4, "_run", side_effect=fake_run):
            result = probe_s4._docker_case("valid_import", ["true"], [])
        self.assertEqual(result["status"], "create_failed")
        self.assertFalse(result["cleanup_verified"])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
