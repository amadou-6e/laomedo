"""Check the committed EXP-89 summary against machine-written evidence."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
import unittest


EVIDENCE_HASHES = {
    "case-a.json": "24baf9d36276f01b7068e5832ed57f14f73dcae8b916d69d6b36a69cad597abe",
    "case-b.json": "4757f687a65192ad873609c7cfd6edf175a698a998543a2f8f53c246b92c5d1c",
    "case-control.json": "093f29e3427417970c38fe9c3aa8df2a10d4b7d6e49e2a9f2ec8bc2222df7b9e",
    "case-b-setup-failure.json": "a242cd27ce7d75869feec0fafae2a5e54a85c92d1ff1daa1c792abf27f2a5182",
    "journal.jsonl": "9902f3058cfaac0e3cc8cd146795001fdc554a130724d7dc2934c3288eecf31c",
}


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parent
        cls.data = json.loads((cls.root / "observation.json").read_text(encoding="utf-8"))
        cls.cases = {name: json.loads((cls.root / "evidence" / name).read_text(encoding="utf-8"))
                     for name in EVIDENCE_HASHES if name.endswith(".json")}
        cls.journal = [json.loads(line) for line in
                       (cls.root / "evidence" / "journal.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_machine_written_evidence_hashes(self):
        for name, expected in EVIDENCE_HASHES.items():
            with self.subTest(name=name):
                digest = hashlib.sha256((self.root / "evidence" / name).read_bytes()).hexdigest()
                self.assertEqual(digest, expected)

    def test_setup_failure_did_not_dispatch(self):
        self.assertEqual(self.data["setup_failure"]["runner_posts"], 0)
        self.assertFalse(self.data["setup_failure"]["counted_as_case"])
        setup = self.cases["case-b-setup-failure.json"]
        self.assertNotIn("send_clicked_utc", setup)
        self.assertEqual(setup["runner_events"], [])

    def test_only_case_a_supports_stop_propagation_result(self):
        a, b, control = (self.data["cases"][name] for name in ("A", "B", "CONTROL"))
        raw_a = self.cases["case-a.json"]
        raw_b = self.cases["case-b.json"]
        raw_control = self.cases["case-control.json"]
        self.assertEqual(len(self.journal), 11)
        self.assertTrue(a["stop_click_completed"])
        self.assertEqual(raw_a["stop_control"]["testId"], "button-stop")
        self.assertEqual(raw_a["stop_clicked_utc"], a["stop_click_utc"])
        a_events = [event for event in self.journal if event["run_id"] == a["runner_run_id"]]
        self.assertEqual([event["kind"] for event in a_events],
                         ["post_received", "ack_held", "ack_sent"])
        self.assertEqual(a_events[0]["at_utc"], a["runner_post_utc"])
        self.assertEqual(a_events[-1]["at_utc"], a["ack_sent_utc"])
        self.assertLess(instant(a["runner_post_utc"]), instant(a["stop_click_utc"]))
        self.assertLess(instant(a["stop_click_utc"]), instant(a["ack_sent_utc"]))
        self.assertLess(instant(a["stop_click_utc"]), instant(raw_a["probe_finished_utc"]))
        self.assertEqual(sum(event["kind"] == "cancel_received" for event in a_events),
                         a["runner_cancels_during_eight_second_window"])
        self.assertFalse(b["stop_click_completed"])
        self.assertIn("locator.click: Timeout", raw_b["probe_error"])
        self.assertEqual(b["interpretation"], "inconclusive_ui_stop_not_clicked")
        self.assertFalse(control["visible_playground_stop_after_completion"])
        self.assertIsNone(raw_control["stop_control"])
        self.assertEqual([event["kind"] for event in self.journal
                          if event["run_id"] == control["runner_run_id"]],
                         ["post_received", "synthetic_effect", "response_sent"])
        self.assertEqual(self.data["model_turns"], 0)


if __name__ == "__main__":
    unittest.main()
