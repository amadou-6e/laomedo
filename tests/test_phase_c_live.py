"""Credential-free checks for the bounded Phase C launch gate."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from experiments.exp22 import phase_c_live, phase_c_kill
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    phase_c_live = phase_c_kill = None


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


if __name__ == "__main__":
    unittest.main()
