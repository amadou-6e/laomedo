"""Root-answer isolation controls; internal native-event inputs only."""

import unittest

from laomedo.agents.agents.codex.utils import _answer


class AnswerTests(unittest.TestCase):
    def test_child_and_unbound_messages_cannot_replace_root_answer(self):
        events = [
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread,
                    "item": {"type": "agentMessage", "text": text},
                },
            }
            for thread, text in (
                ("root", "root answer"),
                ("child", "child answer"),
                (None, "unbound answer"),
            )
        ]
        self.assertEqual(_answer(events, "root"), "root answer")
        self.assertIsNone(_answer(events[1:], "root"))

    def test_latest_message_must_belong_to_requested_thread(self):
        events = [
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread,
                    "item": {"type": "agentMessage", "text": text},
                },
            }
            for thread, text in (
                ("root", "first"),
                ("root", "final"),
                ("child", "unrelated"),
            )
        ]
        self.assertEqual(_answer(events, "root"), "final")
