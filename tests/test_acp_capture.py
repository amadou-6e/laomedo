"""Internal capture controls; these fixtures are not live-provider acceptance."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from laomedo.activity.acp.capture import AcpCapture
from laomedo.activity.runner.feed import read_feed


class AcpCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = AcpCapture(self.root, "host-attempt")
        self.capture.begin("native-session", "test prompt")

    def events(self):
        return [
            item["event"]
            for item in read_feed(self.root / "activity-events.jsonl")["events"]
        ]

    def update(self, **update):
        self.capture.update("native-session", update)

    def test_raw_payload_retained_and_credential_fields_redacted(self):
        self.update(
            sessionUpdate="tool_call",
            toolCallId="native-call",
            title="exec",
            rawInput={
                "command": "echo Bearer private-token",
                "Authorization": "secret",
            },
        )
        events = self.events()
        self.assertEqual(events[3]["method"], "acp/sessionUpdate")
        self.assertEqual(events[3]["params"]["update"]["toolCallId"], "native-call")
        self.assertNotIn("secret", json.dumps(events))
        self.assertNotIn("private-token", json.dumps(events))
        self.assertFalse(
            any(event["method"].startswith("opencode/") for event in events)
        )

    def test_reasoning_and_answer_are_distinct_even_with_same_native_message_id(self):
        for kind, text in [
            ("agent_thought_chunk", "thought"),
            ("agent_message_chunk", "answer"),
        ]:
            self.update(
                sessionUpdate=kind,
                messageId="same",
                content={"type": "text", "text": text},
            )
        self.capture.finish("native-session", "completed")
        items = [
            e["params"]["item"]
            for e in self.events()
            if e["method"] == "item/completed"
        ]
        self.assertEqual(
            [(i["type"], i["text"]) for i in items[1:]],
            [("reasoning", "thought"), ("agentMessage", "answer")],
        )

    def test_tool_deltas_merge_by_observed_identity_and_preserve_final_output(self):
        self.update(
            sessionUpdate="tool_call",
            toolCallId="call",
            title="exec",
            status="pending",
            rawInput={"command": "pwd"},
        )
        self.update(
            sessionUpdate="tool_call_update",
            toolCallId="call",
            status="completed",
            rawOutput={"output": "/draft"},
        )
        item = self.events()[-1]["params"]["item"]
        self.assertEqual(
            (item["id"], item["type"], item["command"], item["aggregatedOutput"]),
            ("call", "commandExecution", "pwd", "/draft"),
        )

    def test_foreign_session_rejected_and_host_attempt_identity_labelled(self):
        with self.assertRaisesRegex(ValueError, "session mismatch"):
            self.capture.update("foreign", {"sessionUpdate": "agent_message_chunk"})
        self.assertEqual(self.events()[1]["params"]["identity_source"], "host_attempt")

    def test_terminal_seals_capture_and_retains_usage_without_guessing_scope(self):
        usage = {"inputTokens": 12, "totalTokens": 18}
        self.capture.finish("native-session", "completed", usage)
        before = self.events()
        self.update(
            sessionUpdate="agent_message_chunk",
            content={"type": "text", "text": "late"},
        )
        self.capture.finish("native-session", "completed", usage)
        self.assertEqual(self.events(), before)
        self.assertEqual(before[-2]["params"]["usage"], usage)
        self.assertFalse(
            any(e["method"] == "thread/tokenUsage/updated" for e in before)
        )

    def test_oversized_record_is_explicit_capture_failure(self):
        with patch("laomedo.activity.acp.capture.MAX_RECORD_BYTES", 150):
            with self.assertRaisesRegex(ValueError, "retention limit"):
                self.update(
                    sessionUpdate="agent_message_chunk",
                    content={"type": "text", "text": "x" * 200},
                )


if __name__ == "__main__":
    unittest.main()
