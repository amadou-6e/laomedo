"""Regression checks for the disposable EXP-100 evidence harness."""

import unittest
from pathlib import Path

from probe import run


class ProbeTests(unittest.TestCase):
    def test_parity_denial_and_no_blind_resend(self):
        evidence = Path(__file__).with_name("observation.json")
        before = evidence.read_bytes() if evidence.exists() else None
        result = run()
        self.assertEqual(result["git_push"]["http_status"], 200)
        self.assertEqual(result["git_fetch"]["http_status"], 200)
        self.assertEqual(result["repeat_uncertain"]["state"], "unknown")
        self.assertFalse(result["repeat_uncertain"]["resent"])
        self.assertEqual(result["changed_request"]["http_status"], 409)
        self.assertEqual(result["secret_export"]["http_status"], 403)
        self.assertEqual(result["revoked"]["http_status"], 403)
        self.assertEqual(result["other_run"]["http_status"], 200)
        self.assertEqual(result["upstream_effect_counts"]["issue_create"], 2)
        self.assertEqual(result["model_turns"], 0)
        self.assertEqual(evidence.read_bytes() if evidence.exists() else None, before)


if __name__ == "__main__":
    unittest.main()
