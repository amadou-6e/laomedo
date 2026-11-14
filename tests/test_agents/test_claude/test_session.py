"""Internal ACP replay boundary controls; no provider is contacted."""

from importlib.util import find_spec
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from laomedo.agents.agents.claude.agent import ClaudeAgent


class ReplaySession:
    """Emit an old load receipt before the current prompt receipt."""

    def __init__(self, session, *, on_extension):
        self.native = on_extension
        self.session_id = "saved-thread"

    async def initialize(self):
        pass

    def emit(self, answer):
        self.native(
            "claude/sdkMessage",
            {
                "sessionId": self.session_id,
                "message": {
                    "type": "result",
                    "session_id": self.session_id,
                    "subtype": "success",
                    "result": answer,
                },
            },
        )

    async def open(self, **kwargs):
        self.emit("old load receipt")

    async def prompt(self, *args, **kwargs):
        self.emit("current receipt")
        return SimpleNamespace(stop_reason="end_turn")

    async def close(self):
        pass


@unittest.skipUnless(find_spec("acp"), "Requires optional ACP dependency")
class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_load_receipts_do_not_enter_current_attempt(self):
        agent = object.__new__(ClaudeAgent)
        agent._event = Mock()
        agent._native_event = Mock()
        record = {
            "thread_id": "saved-thread",
            "active_host_turn": "new-host-turn",
            "requested_model": "test-model",
            "requested_effort": "low",
            "skills": [],
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("laomedo.agents.agents.base.acp.session.AcpSession", ReplaySession),
        ):
            result = await agent._communicate_acp(
                object(),
                Path(temporary),
                record,
                "new task",
                threading.Event(),
                resume=True,
                output_only=True,
                deadline=time.monotonic() + 5,
                telemetry=SimpleNamespace(bind_thread=Mock()),
            )
        self.assertEqual(result["result"], "current receipt")
        agent._native_event.assert_called_once()
        self.assertEqual(
            agent._native_event.call_args.args[2]["result"], "current receipt"
        )
        self.assertTrue(record["_prompt_dispatched"])
