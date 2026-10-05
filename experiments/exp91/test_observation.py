"""Recheck the committed EXP-91 result without starting Docker."""

import json
from pathlib import Path
import unittest


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observation = json.loads(
            Path(__file__).with_name("observation.json").read_text(encoding="utf-8"))

    def test_orphan_survives_sweep_but_not_exact_cleanup(self):
        value = self.observation
        self.assertEqual(value["before_kill_status"], "running")
        self.assertEqual(value["after_restart_status"], "interrupted")
        self.assertEqual(value["after_restart_error"], "runner_restarted")
        self.assertTrue(value["after_restart_container_running"])
        self.assertEqual(value["after_restart_container_id"], value["container_id"])
        self.assertEqual(value["after_restart_container_label"], "exp91")
        self.assertFalse(value["container_name_in_saved_record"])
        self.assertTrue(value["exact_container_absent_after_cleanup"])
        self.assertFalse(value["turn_ledger_exists"])
        self.assertEqual(value["model_turns"], 0)
        self.assertEqual(value["runner_requests"], 1)


if __name__ == "__main__":
    unittest.main()
