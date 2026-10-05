"""Check the committed EXP-89 transcription against its stated conclusion."""

import json
from pathlib import Path
import unittest


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(Path(__file__).with_name("observation.json").read_text())

    def test_setup_failure_did_not_dispatch(self):
        self.assertEqual(self.data["setup_failure"]["runner_posts"], 0)
        self.assertFalse(self.data["setup_failure"]["counted_as_case"])

    def test_only_case_a_supports_stop_propagation_result(self):
        a = self.data["cases"]["A"]
        b = self.data["cases"]["B"]
        control = self.data["cases"]["CONTROL"]
        self.assertTrue(a["stop_click_completed"])
        self.assertLess(a["runner_post_utc"], a["stop_click_utc"])
        self.assertLess(a["stop_click_utc"], a["ack_sent_utc"])
        self.assertEqual(a["runner_cancels_during_eight_second_window"], 0)
        self.assertFalse(b["stop_click_completed"])
        self.assertEqual(b["interpretation"], "inconclusive_ui_stop_not_clicked")
        self.assertFalse(control["visible_playground_stop_after_completion"])
        self.assertEqual(self.data["model_turns"], 0)


if __name__ == "__main__":
    unittest.main()
