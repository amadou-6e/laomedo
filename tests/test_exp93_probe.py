"""Regression guard for the committed one-shot EXP-93 observation."""

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "experiments" / "exp93" / "observation.json"
EXPECTED_SHA256 = "042ce591787d527a80ac5f334696e1e9a071cc45a512ceef8aa7ac9e24f55f64"


class Exp93EvidenceTests(unittest.TestCase):
    def test_committed_observation_and_bound(self):
        raw = OBSERVATION.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        result = json.loads(raw)
        self.assertEqual(result["model_turns"], 0)
        self.assertEqual(result["runner_requests"], 1)
        self.assertTrue(result["reservation_saved_before_kill"])
        self.assertTrue(result["owned_absent_after_kill"])
        self.assertTrue(result["control_survived"])
        self.assertTrue(result["cleanup_verified"])
        self.assertLessEqual(result["cleanup_elapsed_seconds_upper"], 60)
        self.assertEqual(result["after_restart_status"], "interrupted")
        self.assertFalse(result["turn_ledger_exists"])
        self.assertNotEqual(result["owned_id"], result["control_id"])


if __name__ == "__main__":
    unittest.main()
