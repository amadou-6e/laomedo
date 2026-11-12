"""ACP storage/projection controls; no model or fixture acceptance claim."""

import json
from pathlib import Path
import tempfile
import unittest

from laomedo.agents.activity.acp.capture import AcpCapture
from laomedo.agents.activity.projection import project


class AcpCaptureTests(unittest.TestCase):
    def test_long_text_and_reasoning_retain_raw_chunks_with_linear_display_storage(
        self,
    ):
        for kind, item_type in (
            ("agent_message_chunk", "agentMessage"),
            ("agent_thought_chunk", "reasoning"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as private:
                root = Path(private)
                capture = AcpCapture(root, "attempt")
                capture.begin("session", "task")
                chunk = "x" * 100
                for _ in range(1000):
                    capture.update(
                        "session",
                        {
                            "sessionUpdate": kind,
                            "content": {"type": "text", "text": chunk},
                        },
                    )
                path = root / "activity-events.jsonl"
                raw = [json.loads(line) for line in path.read_text().splitlines()]
                events = [
                    {"raw": row["event"], "received_at": row["received_at"]}
                    for row in raw
                ]
                live = project(events, root_thread="session")
                items = [
                    row for row in live["items"] if row["item"].get("type") == item_type
                ]
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["item"]["text"], chunk * 1000)
                capture.finish("session", "completed")
                raw = [json.loads(line) for line in path.read_text().splitlines()]
                updates = [
                    row for row in raw if row["event"]["method"] == "acp/sessionUpdate"
                ]
                self.assertEqual(len(updates), 1000)
                self.assertTrue(
                    all(
                        row["event"]["params"]["update"]["content"]["text"] == chunk
                        for row in updates
                    )
                )
                completed = [
                    row["event"]["params"]["item"]
                    for row in raw
                    if row["event"]["method"] == "item/completed"
                    and row["event"]["params"]["item"].get("type") == item_type
                ]
                self.assertEqual([item["text"] for item in completed], [chunk * 1000])
                self.assertLess(path.stat().st_size, 2 * 1024 * 1024)
