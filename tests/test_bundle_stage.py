"""No-provider checks for bounded frozen-bundle verification and export."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from laomedo.bundle_ingest import HANDOFF_NAME, freeze_run_bundle
from laomedo.bundle_stage import (BundleStageError, MEMORY_BYTES, SCRIPT,
                                  PINNED_IMAGE_ID,
                                  _export_binary, _read_frozen,
                                  _single_bundle_commit,
                                  verify_frozen_bundle)


IMAGE_ID = PINNED_IMAGE_ID


class BundleStageTests(unittest.TestCase):
    def test_export_stream_keeps_binary_bytes_and_rejects_oversize(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "stream.bundle"
            result = _export_binary(
                [sys.executable, "-c",
                 "import sys;sys.stdout.buffer.write(bytes([0,255,10,13]))"],
                output)
            self.assertEqual(result, {"class": "ok", "returncode": 0,
                                      "bytes": 4})
            self.assertEqual(output.read_bytes(), bytes([0, 255, 10, 13]))
            too_large = Path(temporary) / "oversize.bundle"
            result = _export_binary(
                [sys.executable, "-c",
                 "import sys;sys.stdout.buffer.write(b'x'*(32*1024*1024+1))"],
                too_large)
            self.assertEqual(result["class"], "oversized")
            self.assertFalse(too_large.exists())
            timed = Path(temporary) / "timed.bundle"
            result = _export_binary(
                [sys.executable, "-c", "import time;time.sleep(2)"],
                timed, timeout=.2)
            self.assertEqual(result["class"], "timeout")
            self.assertFalse(timed.exists())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.trusted = self.root / "trusted"
        self.agent = self.root / "agent"
        self.trusted.mkdir()
        self._git(self.trusted, "init", "--quiet")
        (self.trusted / "base.txt").write_text("baseline\n", encoding="utf-8")
        self._git(self.trusted, "add", "base.txt")
        self._git(self.trusted, "-c", "user.name=Test", "-c",
                  "user.email=test@example.invalid", "commit", "--quiet", "-m", "base")
        self.baseline = self._git(self.trusted, "rev-parse", "HEAD")
        subprocess.run(["git", "clone", "--quiet", "--no-local", str(self.trusted),
                        str(self.agent)], check=True, capture_output=True)
        self._git(self.agent, "checkout", "--quiet", "-b", "run-branch")
        (self.agent / "agent.txt").write_text("candidate\n", encoding="utf-8")
        self._git(self.agent, "add", "agent.txt")
        self._git(self.agent, "-c", "user.name=Agent", "-c",
                  "user.email=agent@example.invalid", "commit", "--quiet",
                  "-m", "candidate")
        self.commit = self._git(self.agent, "rev-parse", "HEAD")
        self.runner = self.root / "runner-state"
        self.private = self.root / "private-stage"
        self.workspace = self.runner / "runs" / "run-a" / "workspace"
        self.workspace.mkdir(parents=True)
        self.private.mkdir()
        (self.workspace.parent / "record.json").write_text(json.dumps({
            "run_id": "run-a", "status": "completed", "workspace_mode": "git",
            "git_baseline": self.baseline,
            "github_scope": {"repository": "example/disposable",
                             "branch": "run-branch"}}), encoding="utf-8")
        self._git(self.agent, "bundle", "create", str(self.workspace / HANDOFF_NAME),
                  "refs/heads/run-branch")
        self.baseline_bundle = self.root / "baseline.bundle"
        self._git(self.trusted, "bundle", "create", str(self.baseline_bundle), "HEAD")
        self.baseline_hash = hashlib.sha256(self.baseline_bundle.read_bytes()).hexdigest()
        self._git(self.agent, "branch", "validated", self.commit)
        self.exported = self.root / "exported.bundle"
        self._git(self.agent, "bundle", "create", str(self.exported),
                  "refs/heads/validated")
        self.exported_bytes = self.exported.read_bytes()
        self.frozen = freeze_run_bundle(self.runner, self.private, run_id="run-a",
                                        attempt_id="attempt-1")

    def _git(self, directory, *args):
        result = subprocess.run(["git", "-C", str(directory), *args],
                                capture_output=True, check=True)
        return result.stdout.decode().strip()

    def _fake_docker(self, *, network="none", cleanup=True,
                     success=True, output=None, export_class="ok"):
        commands = []
        removed = False
        started = False
        exported = self.exported_bytes if output is None else output
        config = {"Image": IMAGE_ID, "Id": "c" * 64,
                  "HostConfig": {"NetworkMode": network, "ReadonlyRootfs": True,
                                 "Memory": MEMORY_BYTES, "PidsLimit": 32,
                                 "Tmpfs": {"/stage": "rw,nosuid,noexec,size=32m"},
                                 "CapDrop": ["ALL"],
                                 "SecurityOpt": ["no-new-privileges"]},
                  "Config": {"User": "10001:10001",
                             "Labels": {}},
                  "Mounts": [{"Type": "bind", "RW": False,
                              "Destination": target} for target in
                             ("/baseline.bundle", "/input.bundle", "/verify.sh")],
                  "State": {"Running": False, "ExitCode": 0}}

        def run(args, timeout=30):
            nonlocal removed, started
            commands.append(args)
            operation = args[1]
            if operation == "inspect":
                name = commands[0][commands[0].index("--name") + 1]
                config["Name"] = "/" + name
                label = next(value for value in commands[0]
                             if value.startswith("laomedo.bundle-stage-token="))
                config["Config"]["Labels"]["laomedo.bundle-stage-token"] = label.split("=", 1)[1]
                config["State"] = {"Running": started and success and not removed,
                                   "ExitCode": 0 if success else 128}
                config["Config"]["Labels"]["laomedo.bundle-stage"] = \
                    commands[0][commands[0].index("--name") + 1]
                return subprocess.CompletedProcess(
                    args, 1 if (removed and cleanup) else 0,
                    json.dumps([config]), "No such object: removed" if removed and cleanup else "")
            if operation == "start":
                started = True
                return subprocess.CompletedProcess(args, 0, "", "")
            if operation == "logs":
                return subprocess.CompletedProcess(
                    args, 0, "STAGE_VERIFIED\n" if success else
                    "STAGE_FAILED=integrity\n", "")
            if operation == "rm":
                removed = True
            return subprocess.CompletedProcess(args, 0, "", "")

        def export_stream(args, destination, timeout=30):
            commands.append(args)
            if export_class != "ok":
                return {"class": export_class, "returncode": 1}
            if not config["State"]["Running"]:
                return {"class": "command_failed", "returncode": 1}
            Path(destination).write_bytes(exported)
            return {"class": "ok", "returncode": 0, "bytes": len(exported)}

        return run, export_stream, commands

    def _verify(self, docker, export):
        return verify_frozen_bundle(
            self.runner, self.private, run_id="run-a", attempt_id="attempt-1",
            baseline_bundle=self.baseline_bundle,
            expected_baseline_sha256=self.baseline_hash,
            commit=self.commit, image_id=IMAGE_ID, docker=docker,
            export=export)

    def test_bundle_header_is_exactly_one_expected_ref(self):
        self.assertEqual(_single_bundle_commit(
            (self.workspace / HANDOFF_NAME).read_bytes(),
            "refs/heads/run-branch"), self.commit)
        with self.assertRaisesRegex(BundleStageError, "bundle_ref_invalid"):
            _single_bundle_commit((self.workspace / HANDOFF_NAME).read_bytes(),
                                  "refs/heads/other")

    def test_exact_frozen_bundle_exports_private_verified_artifact(self):
        docker, export, commands = self._fake_docker()
        result = self._verify(docker, export)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["container"]["cleanup_verified"])
        self.assertEqual(result["container"]["output_sha256"],
                         hashlib.sha256(self.exported_bytes).hexdigest())
        self.assertTrue(result["container"]["success_marker_seen"])
        self.assertEqual(result["container"]["export_class"], "ok")
        self.assertEqual((self.private / "run-a" / "attempt-1" /
                          "verified.bundle").read_bytes(), self.exported_bytes)
        self.assertEqual(len([call for call in commands if call[1] == "create"]), 1)
        create = " ".join(commands[0])
        self.assertIn("--network none", create)
        self.assertIn("--read-only", create)
        self.assertIn(IMAGE_ID, create)
        self.assertFalse(result["policy_approved"])
        self.assertTrue(any(call[1:4] == ["exec", "--user", "10001:10001"]
                            and call[-2:] == ["cat", "/stage/verified.bundle"]
                            for call in commands))
        self.assertLess(next(i for i, call in enumerate(commands)
                             if call[1] == "exec"),
                        next(i for i, call in enumerate(commands)
                             if call[1] == "rm"))
        self.assertIn("target=/baseline.bundle,readonly", create)
        self.assertNotIn("GH_TOKEN", create)
        self.assertTrue(SCRIPT.is_file())
        with self.assertRaisesRegex(BundleStageError,
                                    "verification_identity_consumed"):
            self._verify(docker, export)
        self.assertEqual(len([call for call in commands if call[1] == "create"]), 1)

    def test_wrong_baseline_hash_refuses_before_docker(self):
        docker, _, commands = self._fake_docker()
        with self.assertRaisesRegex(BundleStageError, "baseline_bundle_changed"):
            verify_frozen_bundle(
                self.runner, self.private, run_id="run-a", attempt_id="attempt-1",
                baseline_bundle=self.baseline_bundle,
                expected_baseline_sha256="0" * 64, commit=self.commit,
                image_id=IMAGE_ID, docker=docker)
        self.assertEqual(commands, [])

    def test_changed_frozen_bytes_refuse_before_docker(self):
        (self.private / "run-a" / "attempt-1" / "input.bundle").write_bytes(b"changed")
        docker, export, commands = self._fake_docker()
        with self.assertRaisesRegex(BundleStageError, "frozen_bundle_changed"):
            self._verify(docker, export)
        self.assertEqual(commands, [])

    def test_unverified_network_config_never_starts_container(self):
        docker, export, commands = self._fake_docker(network="bridge")
        result = self._verify(docker, export)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["container"]["status"], "limit_unverified")
        self.assertFalse(any(call[1] == "start" for call in commands))

    def test_cleanup_failure_keeps_outcome_unknown(self):
        docker, export, _ = self._fake_docker(cleanup=False)
        result = self._verify(docker, export)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["container"]["cleanup_verified"])

    def test_container_exiting_before_copy_cannot_verify_output(self):
        docker, export, commands = self._fake_docker(success=False)
        result = self._verify(docker, export)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["container"]["status"], "verification_failed")
        self.assertFalse(any(call[1] == "exec" for call in commands))
        self.assertFalse((self.private / "run-a" / "attempt-1" /
                          "verified.bundle").exists())

    def test_failed_binary_stream_never_verifies_output(self):
        docker, export, commands = self._fake_docker(
            export_class="command_failed")
        result = self._verify(docker, export)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["container"]["status"], "stream_failed")
        self.assertEqual(result["container"]["export_class"],
                         "command_failed")
        self.assertTrue(result["container"]["cleanup_verified"])
        self.assertFalse((self.private / "run-a" / "attempt-1" /
                          "verified.bundle").exists())
        self.assertTrue(any(call[1] == "rm" for call in commands))

    def test_unreviewed_image_is_refused_before_docker(self):
        docker, _, commands = self._fake_docker()
        with self.assertRaisesRegex(BundleStageError, "stage_identity_invalid"):
            verify_frozen_bundle(
                self.runner, self.private, run_id="run-a", attempt_id="attempt-1",
                baseline_bundle=self.baseline_bundle,
                expected_baseline_sha256=self.baseline_hash, commit=self.commit,
                image_id="sha256:" + "e" * 64, docker=docker)
        self.assertEqual(commands, [])

    def test_exported_wrong_ref_is_not_verified(self):
        candidate = (self.workspace / HANDOFF_NAME).read_bytes()
        docker, export, commands = self._fake_docker(output=candidate)
        result = self._verify(docker, export)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["container"]["status"], "output_invalid")
        self.assertTrue(any(call[1] == "rm" for call in commands))


if __name__ == "__main__":
    unittest.main()
