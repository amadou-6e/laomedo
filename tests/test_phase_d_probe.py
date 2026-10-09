"""Credential-free regression checks for Phase D failure-path cleanup."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from experiments.exp22 import phase_d_live
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    phase_d_live = None


@unittest.skipUnless(phase_d_live is not None, "experiment source is not installed in the wheel")
class PhaseDCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runs = Path(temporary.name) / "runs"
        record = self.runs / "run-a" / "record.json"
        record.parent.mkdir(parents=True)
        self.value = {"status": "running", "container_ownership": {
            "name": "laomedo-codex-exact", "launch_token": "owner-token"}}
        record.write_text(json.dumps(self.value), encoding="utf-8")

    def test_cancel_error_still_triggers_exact_cleanup(self):
        runner = mock.Mock()
        runner.status.return_value = self.value
        runner.cancel.side_effect = RuntimeError("simulated_cancel_failure")
        with mock.patch.object(phase_d_live, "_owned_container_absent", return_value=False), \
                mock.patch.object(phase_d_live, "cleanup_exact", return_value=(True, "removed")) as cleanup:
            rows = phase_d_live._cleanup_runner_runs(runner, self.runs, None,
                                                     wait_seconds=0)
        cleanup.assert_called_once_with("laomedo-codex-exact", "run-a", "owner-token")
        self.assertEqual(rows[0]["cancel_error"], "RuntimeError")
        self.assertTrue(rows[0]["exact_cleanup_verified"])

    def test_status_error_uses_saved_ownership_for_cleanup(self):
        runner = mock.Mock()
        runner.status.side_effect = RuntimeError("simulated_status_failure")
        with mock.patch.object(phase_d_live, "_owned_container_absent", return_value=False), \
                mock.patch.object(phase_d_live, "cleanup_exact", return_value=(True, "removed")) as cleanup:
            rows = phase_d_live._cleanup_runner_runs(runner, self.runs, None,
                                                     wait_seconds=0)
        cleanup.assert_called_once_with("laomedo-codex-exact", "run-a", "owner-token")
        self.assertEqual(rows[0]["status_error"], "RuntimeError")
        self.assertTrue(rows[0]["exact_cleanup_verified"])

    def test_unverified_exact_cleanup_stays_unverified(self):
        runner = mock.Mock()
        runner.status.return_value = self.value
        with mock.patch.object(phase_d_live, "_owned_container_absent", return_value=False), \
                mock.patch.object(phase_d_live, "cleanup_exact", return_value=(False, "mismatch")):
            rows = phase_d_live._cleanup_runner_runs(runner, self.runs, "run-a",
                                                     wait_seconds=0)
        self.assertFalse(rows[0]["exact_cleanup_verified"])
        self.assertEqual(rows[0]["exact_cleanup_detail"], "mismatch")

    def test_route_audit_requires_same_request_and_run(self):
        path = self.runs.parent / "routes.jsonl"
        rows = [{"kind": "start", "path": "/v1/runs/async"},
                {"kind": "lookup", "path": "/v1/requests/request-a"},
                {"kind": "cancel", "path": "/v1/runs/run-a/cancel"}]
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n",
                        encoding="utf-8")
        self.assertTrue(phase_d_live._route_summary(path, "run-a", "request-a")
                        ["exact_identity_match"])
        self.assertFalse(phase_d_live._route_summary(path, "run-b", "request-a")
                         ["exact_identity_match"])
        self.assertFalse(phase_d_live._route_summary(path, "run-a", "request-b")
                         ["exact_identity_match"])


if __name__ == "__main__":
    unittest.main()
