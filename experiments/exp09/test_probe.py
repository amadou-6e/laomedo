"""Acceptance checks for the frozen EXP-09 synthetic replay protocol."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from experiments.exp09.probe import main, run_cases


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="laomedo-exp09-test-")
        self.addCleanup(self.temp.cleanup)
        self.cases = run_cases(Path(self.temp.name) / "cases")

    def test_reconnect_keeps_both_deliveries_without_unique_claim(self):
        case = self.cases["reconnect_replay"]
        self.assertEqual(case["delivery_count"], 2)
        self.assertEqual(case["stream_state"], "complete")
        self.assertEqual([event["source_event_id"] for event in case["events"]],
                         ["evt-1", "evt-1"])
        self.assertEqual(case["events"][0]["payload_sha256"],
                         case["events"][1]["payload_sha256"])
        self.assertEqual(case["action_uniqueness"], "uncertain")
        self.assertIsNone(case["unique_action_count"])

    def test_conflicting_reused_id_keeps_both_payloads(self):
        case = self.cases["conflicting_source_id"]
        self.assertEqual(case["delivery_count"], 2)
        self.assertEqual([event["summary"] for event in case["events"]],
                         ["first payload", "changed payload"])
        self.assertNotEqual(case["events"][0]["payload_sha256"],
                            case["events"][1]["payload_sha256"])
        self.assertIsNone(case["unique_action_count"])

    def test_keyless_reorder_and_crash_remain_partial_and_uncertain(self):
        case = self.cases["keyless_reordered"]
        self.assertEqual(case["delivery_count"], 3)
        self.assertEqual(case["stream_state"], "partial")
        self.assertEqual([event["kind"] for event in case["events"]],
                         ["tool_result", "tool_call", "tool_result"])
        self.assertEqual([event["receipt_sequence"] for event in case["events"]],
                         [1, 2, 3])
        self.assertEqual([event["tool_call_id"] for event in case["events"]],
                         ["call-1", "call-1", "call-1"])
        self.assertTrue(all(event["source_event_id"] is None and
                            event["action_uniqueness"] == "uncertain"
                            for event in case["events"]))
        self.assertTrue(all("linked_to" not in event for event in case["events"]))

    def test_same_source_id_in_distinct_invocations_is_not_collapsed(self):
        cases = self.cases["separate_invocations"]
        for case in cases.values():
            self.assertEqual(case["delivery_count"], 1)
            self.assertEqual(case["stream_state"], "complete")
            self.assertIsNone(case["unique_action_count"])
        self.assertEqual(cases["invocation_1"]["events"][0]["source_event_id"],
                         cases["invocation_2"]["events"][0]["source_event_id"])
        self.assertEqual([cases[key]["events"][0]["kind"] for key in cases],
                         ["tool_call", "tool_result"])
        self.assertEqual([cases[key]["events"][0]["tool_call_id"] for key in cases],
                         ["call-2", "call-2"])
        self.assertTrue(all("linked_to" not in case["events"][0]
                            for case in cases.values()))

    def test_plain_run_does_not_rewrite_pinned_observation(self):
        pinned = Path(__file__).with_name("observation.json")
        before = pinned.read_bytes()
        self.assertEqual(main(), json.loads(before))
        self.assertEqual(pinned.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
