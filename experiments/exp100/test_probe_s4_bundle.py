"""No-Docker preflight and identity tests for S4-03."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp100 import probe_s4_bundle


class ProbeS4BundleTests(unittest.TestCase):
    def test_local_baseline_and_candidate_bundle_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted, candidate, baseline, commit = \
                probe_s4_bundle.probe_s4._fixture(root)
            baseline_bundle = root / "baseline.bundle"
            probe_s4_bundle.create_baseline_bundle(trusted, baseline_bundle)
            probe_s4_bundle.preflight(root, baseline_bundle, candidate,
                                      baseline, commit)
            self.assertGreater(baseline_bundle.stat().st_size, 0)

    def test_failed_record_consumes_distinct_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation-s4-03.json"
            with patch.object(probe_s4_bundle, "run", return_value={
                    "identity": probe_s4_bundle.IDENTITY, "status": "failed"}):
                result = probe_s4_bundle.record_once(target, "c" * 40)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(json.loads(target.read_text())["status"], "failed")
                with self.assertRaises(FileExistsError):
                    probe_s4_bundle.record_once(target, "c" * 40)

    def test_exception_record_does_not_expose_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "observation-s4-03.json"
            with patch.object(probe_s4_bundle, "run",
                              side_effect=RuntimeError("private temp path")):
                probe_s4_bundle.record_once(target, "d" * 40)
            payload = target.read_text()
            self.assertNotIn("private temp path", payload)
            self.assertEqual(json.loads(payload)["error_class"], "RuntimeError")

    def test_container_has_only_the_two_bundle_files_and_script(self):
        inspected = {"Image": probe_s4_bundle.probe_s4.IMAGE_ID,
                     "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True,
                                    "Memory": probe_s4_bundle.probe_s4.MEMORY_BYTES,
                                    "PidsLimit": 32,
                                    "Tmpfs": {"/stage": "rw,size=32m"},
                                    "CapDrop": ["ALL"],
                                    "SecurityOpt": ["no-new-privileges"]},
                     "State": {"ExitCode": 0},
                     "Config": {"Labels": {"laomedo.experiment": "s4"},
                                "User": "10001:10001"},
                     "Mounts": [{"Type": "bind", "RW": False,
                                 "Destination": "/baseline.bundle"},
                                {"Type": "bind", "RW": False,
                                 "Destination": "/input.bundle"},
                                {"Type": "bind", "RW": False,
                                 "Destination": "/verify.sh"}]}
        calls = []
        inspect_count = 0

        def fake_run(args, **_kwargs):
            nonlocal inspect_count
            calls.append(args)
            if args[1] == "inspect":
                inspect_count += 1
                return subprocess.CompletedProcess(
                    args, 1 if inspect_count == 4 else 0,
                    json.dumps([inspected]), "")
            if args[1] == "start":
                return subprocess.CompletedProcess(args, 0,
                                                   "S4_VERIFIED\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(probe_s4_bundle.probe_s4.secrets, "token_hex",
                          return_value="bundle"), \
                patch.object(probe_s4_bundle.probe_s4, "_run",
                             side_effect=fake_run):
            case = probe_s4_bundle.probe_s4._docker_case(
                "valid_import", ["sh", "/verify.sh", "a" * 40, "b" * 40],
                [Path("C:/temp/baseline.bundle"),
                 Path("C:/temp/candidate.bundle")],
                script_path=probe_s4_bundle.SCRIPT,
                trusted_target="/baseline.bundle")
        self.assertEqual(case["status"], "completed")
        self.assertTrue(case["cleanup_verified"])
        self.assertEqual(case["marker"], "S4_VERIFIED")
        self.assertIn("target=/baseline.bundle,readonly", " ".join(calls[0]))
        self.assertNotIn("target=/trusted,readonly", " ".join(calls[0]))


if __name__ == "__main__":
    unittest.main()
