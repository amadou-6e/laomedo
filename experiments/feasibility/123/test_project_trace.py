import importlib.util
from pathlib import Path
import sys
import unittest


SPEC = importlib.util.spec_from_file_location("project_trace", Path(__file__).with_name("project_trace.py"))
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
SANITIZER_SPEC = importlib.util.spec_from_file_location("sanitize_rollout_sample", Path(__file__).with_name("sanitize_rollout_sample.py"))
SANITIZER = importlib.util.module_from_spec(SANITIZER_SPEC)
sys.modules[SANITIZER_SPEC.name] = SANITIZER
SANITIZER_SPEC.loader.exec_module(SANITIZER)


class ProjectionTests(unittest.TestCase):
    def event(self, kind, event_id, when="2026-09-30T12:00:00Z", tool_id=None, status=None, usage=None):
        return MODULE.Envelope("codex-app-server", event_id, when, kind, MODULE.digest([kind, event_id]),
                               "thread-fixture", tool_id, status, usage)

    def test_duplicate_reordered_and_equal_timestamp(self):
        result = MODULE.project("run-fixture", [
            self.event("tool_result", "result-1", tool_id="call-1"),
            self.event("tool_call", "call-1", tool_id="call-1"),
            self.event("tool_result", "result-1", tool_id="call-1"),
            self.event("end", "end-1", status="completed"),
        ])
        self.assertEqual(result["duplicates_ignored"], 1)
        self.assertEqual(result["linked_tool_call_ids"], ["call-1"])
        self.assertEqual([event["sequence"] for event in result["events"]], [0, 1, 2])
        self.assertEqual([event["received_ordinal"] for event in result["events"]], [0, 1, 3])
        self.assertEqual(result["status"], "completed")

    def test_interruption_retains_partial_and_unknown_usage(self):
        result = MODULE.project("run-fixture", [
            self.event("tool_call", "call-1", tool_id="call-1"),
            self.event("usage", "usage-1", usage={"input_tokens": None, "output_tokens": 0}),
        ])
        self.assertEqual(result["status"], "interrupted")
        self.assertFalse(result["trace_complete"])
        self.assertEqual(result["unmatched_tool_call_ids"], ["call-1"])
        self.assertIsNone(result["events"][1]["usage"]["input_tokens"])
        self.assertEqual(result["events"][1]["usage"]["output_tokens"], 0)

    def test_reprojection_preserves_ids_and_raw_digest(self):
        input_events = [self.event("message", "native-1"), self.event("end", "native-2", status="failed")]
        first = MODULE.project("run-fixture", input_events)
        second = MODULE.project("run-fixture", input_events)
        self.assertEqual(first, second)
        self.assertEqual(first["events"][0]["source_event_id"], "native-1")
        self.assertEqual(first["events"][0]["payload_sha256"], input_events[0].payload_sha256)

    def test_same_native_ids_in_different_sources_are_distinct(self):
        a = self.event("message", "same")
        b = MODULE.Envelope("claude-sdk", "same", a.source_time, "message", a.payload_sha256)
        result = MODULE.project("run-fixture", [a, b])
        self.assertEqual(len(result["events"]), 2)

    def test_reused_event_id_with_changed_payload_is_rejected(self):
        original = self.event("message", "same")
        changed = self.event("error", "same")
        with self.assertRaisesRegex(ValueError, "reused"):
            MODULE.project("run-fixture", [original, changed])

    def test_invalid_usage_cannot_look_like_zero(self):
        with self.assertRaises(ValueError):
            self.event("usage", "u", usage={"input_tokens": -1})
        with self.assertRaises(ValueError):
            self.event("usage", "u", usage={"input_tokens": False})

    def test_sanitizer_drops_content_and_rejects_malformed_ids(self):
        import json
        safe = [
            {"type": "session_meta", "payload": {"id": "01234567-89ab-cdef-0123-456789abcdef", "secret": "PRIVATE"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call", "id": "ctc_123456789012", "call_id": "call_123456789012", "input": "PRIVATE"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output", "id": "ctco_123456789012", "call_id": "call_123456789012", "output": "PRIVATE"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call", "id": "ctc_PRIVATE", "call_id": "call_PRIVATE", "input": "PRIVATE"}},
        ]
        result = SANITIZER.sample("\n".join(json.dumps(item) for item in safe))
        self.assertEqual(len(result["pairs"]), 1)
        self.assertNotIn("PRIVATE", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
