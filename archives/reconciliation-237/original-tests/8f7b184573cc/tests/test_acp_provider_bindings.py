"""Internal ACP binding failures; fixture clients are not live acceptance evidence."""

import json
from importlib.util import find_spec
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from laomedo.agents.agents.claude.agent import ClaudeAgent
from laomedo.agents.agents.opencode.boundary import IsolatedOpenCode
from laomedo.agents.agents.opencode.settings import CLI_VERSION
from laomedo.agents.agents.opencode.utils import model_metadata
from laomedo.agents.errors import RunnerError


@unittest.skipUnless(find_spec("acp"), "Requires the optional runner ACP dependency")
class ProviderBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_claude_buffers_receipts_until_bound_and_requires_one_terminal(self):
        for count, stop, mismatch, error in (
            (1, "end_turn", False, None),
            (0, "end_turn", False, "claude_terminal_receipt_invalid"),
            (2, "end_turn", False, "claude_terminal_receipt_invalid"),
            (1, "cancelled", False, "claude_cancelled"),
            (1, "end_turn", True, "claude_session_identity_mismatch"),
        ):
            with (
                self.subTest(count=count, stop=stop, mismatch=mismatch),
                tempfile.TemporaryDirectory() as directory,
            ):
                runner = ClaudeAgent.__new__(ClaudeAgent)
                runner._event = Mock()
                runner._native_event = Mock()
                identity = "11111111-1111-4111-8111-111111111111"
                record = {
                    "thread_id": None,
                    "requested_model": "sonnet",
                    "requested_effort": "low",
                    "skills": [],
                    "active_host_turn": "host-attempt",
                }
                receipt = {
                    "type": "result",
                    "subtype": "success",
                    "session_id": identity,
                    "result": "Internal receipt",
                    "is_error": False,
                }
                client = SimpleNamespace(
                    session_id=identity,
                    initialize=AsyncMock(),
                    open=AsyncMock(),
                    prompt=AsyncMock(return_value=SimpleNamespace(stop_reason=stop)),
                    close=AsyncMock(),
                )

                def factory(session, **callbacks):
                    client.on_extension = callbacks["on_extension"]
                    return client

                async def emit_before_binding(**kwargs):
                    self.assertIsNone(record["thread_id"])
                    for _ in range(count):
                        client.on_extension(
                            "claude/sdkMessage",
                            {
                                "sessionId": "other" if mismatch else identity,
                                "message": receipt,
                            },
                        )
                    runner._native_event.assert_not_called()

                client.open.side_effect = emit_before_binding
                with patch(
                    "laomedo.agents.agents.base.acp.session.AcpSession",
                    side_effect=factory,
                ):
                    operation = runner._communicate_acp(
                        Mock(),
                        Path(directory),
                        record,
                        "Internal task",
                        threading.Event(),
                        time.monotonic() + 10,
                        Mock(),
                        resume=False,
                        output_only=False,
                    )
                    if error:
                        with self.assertRaisesRegex(RunnerError, error):
                            await operation
                    else:
                        self.assertEqual((await operation)["session_id"], identity)
                        self.assertEqual(record["thread_id"], identity)
                        runner._native_event.assert_called_once()
                client.close.assert_awaited_once()

    async def test_opencode_refuses_runtime_and_model_mismatch_before_capture_or_prompt(
        self,
    ):
        for version, observed, error in (
            ("wrong", "provider/model", "opencode_runtime_pin_mismatch"),
            (CLI_VERSION, "provider/other", "opencode_model_not_connected"),
            (CLI_VERSION, "provider/model", None),
        ):
            with self.subTest(version=version, observed=observed):
                runner = IsolatedOpenCode.__new__(IsolatedOpenCode)
                runner.session = Mock()
                runner.check_transport = Mock()
                client = SimpleNamespace(
                    session_id="native-session",
                    on_update=None,
                    initialize=AsyncMock(
                        return_value=SimpleNamespace(
                            agent_info=SimpleNamespace(version=version)
                        )
                    ),
                    open=AsyncMock(
                        return_value=SimpleNamespace(
                            config_options=[
                                SimpleNamespace(category="model", id="model")
                            ]
                        )
                    ),
                    configure=AsyncMock(
                        return_value=SimpleNamespace(
                            config_options=[
                                SimpleNamespace(id="model", current_value=observed)
                            ]
                        )
                    ),
                    prompt=AsyncMock(
                        return_value=SimpleNamespace(stop_reason="end_turn", usage=None)
                    ),
                    close=AsyncMock(),
                )
                order = []
                capture = Mock()
                capture.begin.side_effect = lambda *args: order.append("capture")
                on_session = Mock(side_effect=lambda *args: order.append("bind"))

                async def prompt_after_binding(*args, **kwargs):
                    self.assertEqual(order, ["bind", "capture"])
                    self.assertEqual(client.on_update, capture.update)
                    return SimpleNamespace(stop_reason="end_turn", usage=None)

                client.prompt.side_effect = prompt_after_binding
                with patch(
                    "laomedo.agents.agents.base.acp.session.AcpSession",
                    return_value=client,
                ):
                    operation = runner._run_acp(
                        "Internal task",
                        "provider/model",
                        None,
                        threading.Event(),
                        capture,
                        on_session,
                    )
                    if error:
                        with self.assertRaisesRegex(RunnerError, error):
                            await operation
                        client.prompt.assert_not_awaited()
                        capture.begin.assert_not_called()
                        on_session.assert_not_called()
                    else:
                        await operation
                        capture.finish.assert_called_once_with(
                            "native-session", "completed", None
                        )
                client.close.assert_awaited_once()

    def test_native_model_metadata_rejects_conflicting_or_incomplete_ids(self):
        valid = "provider/model\n" + json.dumps(
            {"providerID": "provider", "id": "model"}
        )
        self.assertEqual(model_metadata(valid)[0]["id"], "provider/model")
        for value in (
            "",
            "provider/model\n{}",
            valid + "\n" + valid,
            "provider/other\n" + json.dumps({"providerID": "provider", "id": "model"}),
        ):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(RunnerError, "opencode_model_not_connected"),
            ):
                model_metadata(value)
