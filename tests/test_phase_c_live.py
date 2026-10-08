"""Credential-free checks for the bounded Phase C launch gate."""

import tempfile
from pathlib import Path
import json
import threading
import time
import unittest
from unittest.mock import patch

try:
    from experiments.exp22 import phase_c_live, phase_c_kill, phase_c_fake_host
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    phase_c_live = phase_c_kill = phase_c_fake_host = None


@unittest.skipUnless(phase_c_live is not None, "experiment source is not installed in the wheel")
class PhaseCLiveGateTests(unittest.TestCase):
    def test_shared_budget_counts_uncertain_submissions_across_states(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                phase_c_live, "BUDGET", Path(directory) / "turns.json"):
            attempts = []
            for index in range(4):
                attempt, count = phase_c_live._budget_update(
                    state=Path(directory) / f"run-{index}")
                attempts.append(attempt)
                self.assertEqual(count, index + 1)
            with self.assertRaisesRegex(RuntimeError, "budget_exhausted"):
                phase_c_live._budget_update(state=Path(directory) / "fifth")
            _, count = phase_c_live._budget_update(
                attempt_id=attempts[0], result="timeout")
            self.assertEqual(count, 4)
            with self.assertRaisesRegex(RuntimeError, "budget_exhausted"):
                phase_c_live._budget_update(state=Path(directory) / "sixth")

    def test_login_denial_requires_completed_command_output(self):
        command = "cat /home/runner/.codex/auth.json >/dev/null 2>&1"
        def event(output):
            return {"method": "item/completed", "params": {"item": {
                "type": "commandExecution", "command": command,
                "exitCode": 0, "aggregatedOutput": output}}}
        self.assertEqual(phase_c_live._auth_read_result([event(
            "AUTH_READ_EXIT=1\n")]), ("denied", 0))
        self.assertEqual(phase_c_live._auth_read_result([event(
            "AUTH_READ_EXIT=0\n")]), ("readable", 0))
        self.assertEqual(phase_c_live._auth_read_result([]), ("missing", None))
        self.assertEqual(phase_c_live._auth_read_result([event(
            "no probe result")]), ("unverified", 0))

    def test_cleanup_attribution_does_not_promote_self_removal(self):
        self.assertEqual(phase_c_kill._cleanup_attribution({
            "state": "removed_after_loss", "cleanup_verified": True}), "service")
        for state in ("never_observed", "self_removed_after_observed"):
            self.assertEqual(phase_c_kill._cleanup_attribution({
                "state": state, "cleanup_verified": False}), "inconclusive")
        self.assertEqual(phase_c_kill._cleanup_attribution({
            "state": "unknown", "cleanup_verified": False}), "failed")

    def test_agent_request_hold_releases_only_after_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lease_dir = root / "lease" / "leases" / "synthetic"
            lease_dir.mkdir(parents=True)
            run_id = "00000000-0000-4000-8000-000000000001"
            (lease_dir / "lease.json").write_text(
                json.dumps({"run_id": run_id}), encoding="utf-8")
            claimed = root / ".laomedo-req-phase-c-kill-1.json"
            claimed.write_text("{}", encoding="utf-8")
            barrier = root / "held.json"
            bridge = phase_c_fake_host.HeldAgentRequestBridge(
                root, root / "lease", None, None, root / "journal.jsonl",
                held_effect="phase-c-kill-1", barrier=barrier)
            processed = []
            with patch.object(phase_c_fake_host.FileMediationBridge, "_process",
                              side_effect=lambda *args: processed.append(args)):
                worker = threading.Thread(target=bridge._process, args=(
                    run_id, "phase-c-kill-1", claimed, root, "synthetic"))
                worker.start()
                deadline = time.monotonic() + 2
                while not barrier.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(barrier.exists())
                self.assertEqual(processed, [])
                (lease_dir / "revoked.json").write_text("{}", encoding="utf-8")
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(processed), 1)


if __name__ == "__main__":
    unittest.main()
