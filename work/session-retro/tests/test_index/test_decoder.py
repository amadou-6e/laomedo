"""Actual-shape regression controls discovered during native schema inventory."""

import ast
import hashlib
from pathlib import Path
import unittest

from session_retro.decoder import CodexEventDecoder
from session_retro.models import RecordLocator, SourceRecord
from session_retro.settings import ERROR_MESSAGES, Settings
from support.utils import exec_output, record


class DecoderTests(unittest.TestCase):
    """Control wrapper interpretation without presenting synthetic outcomes as real."""

    def test_text_block_tool_results_preserve_failure_and_success(self):
        """Recognize status JSON inside actual-shape native output block lists."""
        decoder = CodexEventDecoder(Settings())
        for exit_code in (0, 1):
            data = record(
                "response_item",
                {
                    "type": "custom_tool_call_output",
                    "call_id": "c1",
                    "output": exec_output(exit_code, "actual body"),
                },
            )
            loc = RecordLocator(
                line=1,
                offset=0,
                length=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                prefix_sha256=hashlib.sha256(data).hexdigest(),
            )
            event = decoder.decode(SourceRecord(locator=loc, data=data))
            self.assertEqual(event.failure, exit_code != 0)
            self.assertIn("actual body", event.text)

    def test_stdout_status_is_opaque_and_unsupported_formats_remain_unknown(self):
        """Printed errors/successes cannot change a recognized wrapper outcome."""
        samples = [
            (
                exec_output(
                    0, '{"exit_code":1,"status":"failed"}\nProcess exited with code 1'
                ),
                False,
            ),
            (exec_output(1, '{"exit_code":0}\nProcess exited with code 0'), True),
            (exec_output(None, '{"exit_code":1}'), None),
            ('{"exit_code":0}', None),
            ("Process exited with code 1\n", None),
            ({"metadata": {"status": "failed"}}, None),
            ([{"type": "input_text", "text": '{"exit_code":1}'}], None),
        ]
        for output, expected in samples:
            with self.subTest(expected=expected):
                data = record(
                    "response_item",
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "c1",
                        "output": output,
                    },
                )
                locator = RecordLocator(
                    line=1,
                    offset=0,
                    length=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    prefix_sha256=hashlib.sha256(data).hexdigest(),
                )
                event = CodexEventDecoder(Settings()).decode(
                    SourceRecord(locator=locator, data=data)
                )
                self.assertIs(event.failure, expected)

    def test_phase_and_native_turn_identity_are_preserved(self):
        """Final answers remain distinguishable from commentary without inference."""
        data = record(
            "response_item",
            {
                "type": "message",
                "id": "native-item",
                "role": "assistant",
                "phase": "final_answer",
                "internal_chat_message_metadata_passthrough": {
                    "turn_id": "native-turn"
                },
                "content": [{"text": "done"}],
            },
        )
        loc = RecordLocator(
            line=1,
            offset=0,
            length=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            prefix_sha256=hashlib.sha256(data).hexdigest(),
        )
        event = CodexEventDecoder(Settings()).decode(
            SourceRecord(locator=loc, data=data)
        )
        self.assertEqual(
            (event.phase, event.turn_id, event.message_id),
            ("final_answer", "native-turn", "native-item"),
        )

    def test_each_local_error_producer_has_a_descriptive_explanation(self):
        """Reject newly introduced bare codes without a safe shared explanation."""
        root = Path(__file__).resolve().parents[2] / "session_retro"
        codes = set()
        for path in root.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "RetrospectiveError"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    codes.add(node.args[0].value)
        self.assertTrue(codes)
        self.assertFalse(codes - set(ERROR_MESSAGES))
        self.assertTrue(all(" " in ERROR_MESSAGES[c] for c in codes))
