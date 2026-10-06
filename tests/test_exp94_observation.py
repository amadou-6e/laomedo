"""Check committed EXP-94 machine evidence, not a hand-written summary."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import unittest


EVIDENCE = Path(__file__).resolve().parents[1] / "experiments" / "exp94" / "evidence"
HASHES = {
    "case-a.json": "7a12bd36b7a64da5530f8ba88e8ed64588d91b2643d54b5e1acf58b950622533",
    "case-b.json": "62dd9ea8722a0a67b23c2e2a385cc0603ad060e3581e63518a65c809318fd909",
    "case-control.json": "8601db3000bfebcd941b9c31fdff8ad014075d4040fc7d43c3b728e473f6a12e",
    "case-control_late.json": "82aa5ea95f7fe966df9a5ed06e5ec24772583b3f3b5b94c9acf80124b6b6d02e",
    "journal.jsonl": "0a24849c5badb341fc92c570f9728454f702dceda0c872bbf8560c2ff9ea27f2",
}


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Exp94ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name, digest in HASHES.items():
            raw = (EVIDENCE / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise AssertionError("evidence_hash_mismatch:" + name)
        cls.cases = {name: json.loads((EVIDENCE / ("case-" + name.lower() + ".json"))
                                      .read_text(encoding="utf-8"))
                     for name in ("A", "B", "CONTROL", "CONTROL_LATE")}
        cls.journal = [json.loads(line) for line in (EVIDENCE / "journal.jsonl")
                       .read_text(encoding="utf-8").splitlines() if line]

    def events(self, case):
        run_id = self.cases[case]["target_event"]["run_id"]
        return [event for event in self.journal if event.get("run_id") == run_id]

    def test_active_stop_links_one_start_lookup_and_cancel_per_case(self):
        for name in ("A", "B"):
            with self.subTest(name=name):
                case = self.cases[name]
                self.assertNotIn("probe_error", case)
                self.assertEqual(case["stop_control"]["testId"], "button-stop")
                events = self.events(name)
                kinds = [event["kind"] for event in events]
                self.assertEqual(kinds.count("post_received"), 1)
                self.assertFalse(next(e for e in events if e["kind"] == "post_received")["duplicate"])
                self.assertEqual(kinds.count("request_lookup"), 1)
                self.assertEqual(kinds.count("cancel_received"), 1)
                self.assertTrue(next(e for e in events if e["kind"] == "cancel_received")["known"])
                self.assertNotIn("synthetic_effect", kinds)
                self.assertLess(instant(case["target_event"]["at_utc"]),
                                instant(case["stop_clicked_utc"]))
                self.assertLess(instant(case["stop_clicked_utc"]),
                                instant(next(e for e in events if e["kind"] == "cancel_received")["at_utc"]))
                if name == "A":
                    self.assertLess(instant(next(e for e in events if e["kind"] == "cancel_received")["at_utc"]),
                                    instant(next(e for e in events if e["kind"] == "ack_sent")["at_utc"]))

    def test_completed_controls_have_no_cancel_or_duplicate_start(self):
        for name in ("CONTROL", "CONTROL_LATE"):
            with self.subTest(name=name):
                case = self.cases[name]
                self.assertNotIn("probe_error", case)
                events = self.events(name)
                kinds = [event["kind"] for event in events]
                self.assertEqual(kinds.count("post_received"), 1)
                self.assertEqual(kinds.count("synthetic_effect"), 1)
                self.assertEqual(kinds.count("cancel_received"), 0)
                if name == "CONTROL_LATE":
                    self.assertEqual(case["stop_control"]["testId"], "button-stop")
                    self.assertLess(instant(next(e for e in events if e["kind"] == "synthetic_effect")["at_utc"]),
                                    instant(case["stop_clicked_utc"]))
                else:
                    self.assertNotIn("stop_clicked_utc", case)

    def test_all_cases_use_distinct_native_runs(self):
        ids = [self.cases[name]["target_event"]["run_id"] for name in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sum(e["kind"] == "post_received" for e in self.journal), 4)
        self.assertEqual(sum(e["kind"] == "cancel_received" for e in self.journal), 2)


if __name__ == "__main__":
    unittest.main()
