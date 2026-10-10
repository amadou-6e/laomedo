"""Credential-free worker controls; fake stage, no Docker or provider effects."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from laomedo.bundle_ingest import freeze_run_bundle, HANDOFF_NAME, _durable_json
from laomedo.bundle_verifier import BundleVerifier, _publish_status
from laomedo.bundle_stage import BundleStageError


class BundleVerifierTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runner = self.root / "runner"
        self.private = self.root / "private"
        self.private.mkdir()
        self.workspace = self.runner / "runs" / "run-a" / "workspace"
        self.workspace.mkdir(parents=True)
        self.record_path = self.workspace.parent / "record.json"
        self.record = {"run_id": "run-a", "status": "running", "workspace_mode": "git",
            "git_baseline": "a" * 40,
            "github_scope": {"repository": "example/disposable", "branch": "branch-a"},
            "container_ownership": {"name": "owned-a", "launch_token": "launch-a",
                "grant_id": "grant-a", "supervised": True, "cleanup_verified": False}}
        self.record_path.write_text(json.dumps(self.record), encoding="utf-8")
        (self.workspace / HANDOFF_NAME).write_bytes(
            b"# v2 git bundle\n" + b"b" * 40 + b" refs/heads/branch-a\n\nsynthetic-pack")
        freeze_run_bundle(self.runner, self.private, run_id="run-a", attempt_id="attempt-a")
        self.baseline = self.root / "baseline.bundle"
        self.baseline.write_bytes(b"synthetic-baseline")
        self.calls = []

    def worker(self, mutation=None):
        def verify(runner, private, **kwargs):
            self.calls.append(kwargs)
            result = {"status": "verified", "run_id": kwargs["run_id"],
                      "attempt_id": kwargs["attempt_id"]}
            _durable_json(private / "run-a" / "attempt-a" / "verification.json", result)
            if mutation:
                mutation()
            return result
        return BundleVerifier(self.runner, self.private, agent_mount=self.root / "agent",
            baseline_bundle=self.baseline,
            baseline_sha256=hashlib.sha256(self.baseline.read_bytes()).hexdigest(), verify=verify)

    def test_worker_uses_frozen_identity_and_never_retries_reserved_attempt(self):
        worker = self.worker()
        self.assertEqual(worker.scan_once(), [{"run_id": "run-a", "attempt_id": "attempt-a", "status": "verified"}])
        self.assertEqual(worker.scan_once(), [])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["commit"], "b" * 40)
        self.assertNotIn("token", self.calls[0])

    def test_changed_active_binding_cannot_be_reported_verified(self):
        def change():
            self.record["status"] = "completed"
            self.record_path.write_text(json.dumps(self.record), encoding="utf-8")
        self.assertEqual(self.worker(change).scan_once()[0]["status"], "unknown")
        saved = json.loads((self.private / "run-a" / "attempt-a" / "verification.json").read_bytes())
        self.assertEqual(saved["error_class"], "run_binding_changed")

    def test_partial_freeze_or_consumed_verification_is_not_dispatched(self):
        attempt = self.private / "run-a" / "attempt-a"
        (attempt / "verification.json.pending").write_bytes(b"reserved")
        self.assertEqual(self.worker().scan_once(), [])
        self.assertEqual(self.calls, [])

    def test_another_worker_cannot_dispatch_a_claimed_attempt(self):
        attempt = self.private / "run-a" / "attempt-a"
        (attempt / "verifier-claim.json").write_bytes(b"crashed-worker-claim")
        self.assertEqual(self.worker().scan_once(), [])
        self.assertEqual(self.calls, [])

    def test_prejournal_rejection_is_recorded_without_retry(self):
        worker = self.worker()
        def refuse(*_args, **_kwargs):
            raise BundleStageError("baseline_bundle_changed")
        worker.verify = refuse
        self.assertEqual(worker.scan_once()[0]["status"], "failed")
        attempt = self.private / "run-a" / "attempt-a"
        self.assertEqual(json.loads((attempt / "verification.json").read_bytes())["error_class"], "BundleStageError")
        self.assertEqual(worker.scan_once(), [])

    def test_unexpected_attempt_failure_does_not_abort_worker_scan(self):
        workspace_b = self.runner / "runs" / "run-b" / "workspace"
        workspace_b.mkdir(parents=True)
        (workspace_b.parent / "record.json").write_text(
            json.dumps({**self.record, "run_id": "run-b"}), encoding="utf-8")
        (workspace_b / HANDOFF_NAME).write_bytes((self.workspace / HANDOFF_NAME).read_bytes())
        freeze_run_bundle(self.runner, self.private, run_id="run-b", attempt_id="attempt-b")
        worker = self.worker()
        def broken(*_args, **_kwargs):
            raise TypeError("synthetic-malformed-record")
        worker.verify = broken
        statuses = worker.scan_once()
        self.assertEqual(len(statuses), 2)
        self.assertEqual({item["status"] for item in statuses}, {"unknown"})
        self.assertEqual(worker.scan_once(), [])

    def test_tampered_frozen_bytes_or_completed_run_never_reaches_stage(self):
        attempt = self.private / "run-a" / "attempt-a"
        original = (attempt / "input.bundle").read_bytes()
        (attempt / "input.bundle").write_bytes(b"tampered")
        self.assertEqual(self.worker().scan_once(), [])
        (attempt / "input.bundle").write_bytes(original)
        self.record["status"] = "completed"
        self.record_path.write_text(json.dumps(self.record), encoding="utf-8")
        self.assertEqual(self.worker().scan_once(), [])
        self.assertEqual(self.calls, [])

    def test_baseline_in_agent_mount_is_refused(self):
        with self.assertRaisesRegex(ValueError, "verifier_boundary_invalid"):
            BundleVerifier(self.runner, self.private, agent_mount=self.root,
                baseline_bundle=self.baseline, baseline_sha256="a" * 64)

    def test_service_status_is_fresh_host_only_and_does_not_redispatch(self):
        worker = self.worker()
        stopping = threading.Event()
        observed = []
        original = worker.scan_once

        def scan():
            observed.append(json.loads((self.private / "service-status.json").read_bytes()))
            result = original()
            if len(observed) == 2:
                stopping.set()
            return result

        with patch.object(worker, "scan_once", scan):
            worker.serve(stopping)
        final = json.loads((self.private / "service-status.json").read_bytes())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(observed), 2)
        self.assertIsNone(observed[0]["scan_completed_monotonic"])
        self.assertLessEqual(observed[0]["scan_started_monotonic"],
                             observed[1]["scan_completed_monotonic"])
        self.assertLessEqual(observed[1]["scan_completed_monotonic"],
                             observed[1]["scan_started_monotonic"])
        self.assertEqual(final["phase"], "stopped")
        self.assertEqual(final["instance"], observed[0]["instance"])
        self.assertRegex(final["instance"], r"^[0-9a-f]{32}$")
        self.assertEqual(set(final), {"instance", "pid", "module_root", "phase",
            "started_monotonic", "scan_started_monotonic", "scan_completed_monotonic"})
        self.assertEqual(Path(final["module_root"]).resolve(),
                         Path(__file__).resolve().parents[1] / "laomedo")
        self.assertFalse((self.workspace / "service-status.json").exists())
        self.assertNotIn("grant-a", json.dumps(final))

    def test_service_failure_marks_stopped_without_completed_scan(self):
        worker = self.worker()
        with patch.object(worker, "scan_once", side_effect=RuntimeError("synthetic-failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic-failure"):
                worker.serve(threading.Event())
        final = json.loads((self.private / "service-status.json").read_bytes())
        self.assertEqual(final["phase"], "stopped")
        self.assertIsNone(final["scan_completed_monotonic"])
        self.assertNotIn("synthetic-failure", json.dumps(final))

    def test_status_replacement_retries_reader_lock_and_preserves_old_pending(self):
        import os
        path = self.private / "service-status.json"
        leftover = path.with_name(path.name + ".pending-old-worker")
        leftover.write_bytes(b"old diagnostic only")
        original = os.replace
        calls = []

        def replace(source, target):
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError("synthetic-reader-lock")
            return original(source, target)

        with patch("laomedo.bundle_verifier.os.replace", replace):
            _publish_status(path, {"phase": "idle"})
        self.assertEqual(json.loads(path.read_bytes()), {"phase": "idle"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(leftover.read_bytes(), b"old diagnostic only")
        self.assertEqual(list(self.private.glob("service-status.json.pending-*")), [leftover])


if __name__ == "__main__":
    unittest.main()
