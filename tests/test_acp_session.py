"""Internal protocol controls; these do not establish live provider acceptance."""

import asyncio
import json
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

try:
    from acp import RequestError
    from laomedo.agents.agents.base.acp.session import AcpSession
    from laomedo.agents.agents.base.acp.transport import DockerTransport
except ImportError:
    AcpSession = None


@unittest.skipIf(AcpSession is None, "Optional runner ACP dependency is not installed")
class AcpSessionTests(unittest.IsolatedAsyncioTestCase):
    """Guard the shared trust boundary, resume binding and terminal semantics."""

    def setUp(self):
        self.container = Mock()
        self.connection = SimpleNamespace(
            initialize=AsyncMock(
                return_value=SimpleNamespace(
                    protocol_version=1,
                    agent_capabilities=SimpleNamespace(load_session=True),
                )
            ),
            new_session=AsyncMock(
                return_value=SimpleNamespace(session_id="native-session")
            ),
            load_session=AsyncMock(return_value=SimpleNamespace()),
            set_config_option=AsyncMock(),
            cancel=AsyncMock(),
            close=AsyncMock(),
        )
        with patch(
            "laomedo.agents.agents.base.acp.session.connect_to_agent",
            return_value=self.connection,
        ):
            self.client = AcpSession(self.container)

    async def test_initialize_advertises_no_host_filesystem_or_terminal(self):
        await self.client.initialize()
        capabilities = self.connection.initialize.call_args.kwargs[
            "client_capabilities"
        ]
        self.assertFalse(capabilities.terminal)
        self.assertFalse(capabilities.fs.read_text_file)
        self.assertFalse(capabilities.fs.write_text_file)
        for method in (
            "create_terminal",
            "read_text_file",
            "write_text_file",
            "kill_terminal",
        ):
            self.assertFalse(hasattr(self.client, method))

    async def test_permissions_are_denied_even_if_agent_offers_allow(self):
        response = await self.client.request_permission(
            "native-session", {}, [{"optionId": "allow", "kind": "allow_always"}]
        )
        self.assertEqual(response.outcome.outcome, "cancelled")
        self.container.assert_not_called()

    async def test_extension_requests_cannot_execute_tools(self):
        with self.assertRaises(RequestError):
            await self.client.ext_method("terminal/create", {"command": "anything"})

    async def test_precheck_is_opt_in_and_other_extensions_stay_denied(self):
        with self.assertRaises(RequestError):
            await self.client.ext_method("laomedo/outputPrecheck", {})
        self.client.on_precheck = Mock(
            return_value={"success": True, "contentItems": []}
        )
        params = {"threadId": "native-session", "callId": "native-call"}
        response = await self.client.ext_method("laomedo/outputPrecheck", params)
        self.assertTrue(response["success"])
        self.client.on_precheck.assert_called_once_with(params)
        with self.assertRaises(RequestError):
            await self.client.ext_method("laomedo/exec", {"command": "anything"})

    async def test_precheck_failure_is_safe_and_invalidates_protocol_success(self):
        self.client.on_precheck = Mock(side_effect=ValueError("private native payload"))
        with self.assertRaises(RequestError) as caught:
            await self.client.ext_method("laomedo/outputPrecheck", {})
        self.assertNotIn("private", str(caught.exception))
        self.assertTrue(self.client.protocol_failed)

    async def test_notification_capture_failures_do_not_reach_sdk_logging(self):
        self.client.session_id = "actual"
        self.client.on_update = Mock(side_effect=ValueError("private payload"))
        with self.assertNoLogs():
            await self.client.session_update("actual", Mock())
            await self.client.session_update("unrelated", Mock())
            self.client.on_extension = Mock(side_effect=ValueError("secret"))
            await self.client.ext_notification("codexEvent", {})
        self.assertTrue(self.client.protocol_failed)

    async def test_resume_requires_advertised_support_and_never_creates_fresh(self):
        await self.client.initialize()
        self.client.capabilities.load_session = False
        with self.assertRaisesRegex(ValueError, "resume_provider_binding_mismatch"):
            await self.client.open(session_id="saved-native-id")
        self.connection.new_session.assert_not_called()
        self.connection.load_session.assert_not_called()

    async def test_resume_passes_existing_native_id_and_discards_replay(self):
        await self.client.initialize()
        self.client.updates.append({"old": "history"})
        await self.client.open(session_id="saved-native-id")
        self.assertEqual(self.client.session_id, "saved-native-id")
        self.connection.load_session.assert_awaited_once_with(
            session_id="saved-native-id", cwd="/draft", mcp_servers=[]
        )
        self.connection.new_session.assert_not_called()
        self.assertEqual(self.client.updates, [])

    async def test_close_removes_container_before_sdk_receiver_shutdown(self):
        order = []
        self.container.close.side_effect = lambda: order.append("container")
        self.connection.close.side_effect = lambda: order.append("sdk")
        await self.client.close()
        self.assertEqual(order, ["container", "sdk"])

    async def test_close_preserves_cleanup_failure_and_still_closes_sdk(self):
        self.container.close.side_effect = RuntimeError("cleanup uncertain")
        with self.assertRaisesRegex(RuntimeError, "cleanup uncertain"):
            await self.client.close()
        self.connection.close.assert_awaited_once()

    async def test_timeout_uses_safe_existing_code(self):
        with self.assertRaisesRegex(ValueError, "request_timeout:initialize"):
            await self.client._request(asyncio.sleep(10), "initialize", 0.001)

    async def test_external_error_does_not_leak_payload_or_invent_cause(self):
        request = AsyncMock(
            side_effect=RequestError.internal_error({"secret": "private"})
        )
        with self.assertRaisesRegex(ValueError, "^runner_transport_failed$"):
            await self.client._request(request(), "initialize", 1)

    async def test_prompt_cancellation_waits_for_native_terminal_response(self):
        await self.client.initialize()
        await self.client.open()
        done = asyncio.Event()

        async def prompt(**kwargs):
            await done.wait()
            return SimpleNamespace(stop_reason="cancelled", usage=None)

        self.connection.prompt = prompt
        self.connection.cancel.side_effect = lambda **kwargs: done.set()
        cancelled = threading.Event()
        cancelled.set()
        result = await self.client.prompt("task", cancelled=cancelled, seconds=1)
        self.assertEqual(result.stop_reason, "cancelled")
        self.assertTrue(self.client.cancel_sent)
        self.connection.cancel.assert_awaited_once_with(session_id="native-session")

    async def test_answer_contains_only_current_agent_text(self):
        await self.client.initialize()
        await self.client.open()

        async def prompt(**kwargs):
            self.client.updates.extend(
                [
                    {
                        "sessionUpdate": "agent_thought_chunk",
                        "content": {"type": "text", "text": "private reasoning"},
                    },
                    {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "actual answer"},
                    },
                ]
            )
            return SimpleNamespace(stop_reason="end_turn", usage=None)

        self.connection.prompt = prompt
        self.client.updates.append(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "earlier answer"},
            }
        )
        result = await self.client.prompt(
            "task", cancelled=threading.Event(), seconds=1
        )
        self.assertEqual(result.answer, "actual answer")

    async def test_host_health_failure_cancels_and_preserves_its_safe_code(self):
        from laomedo.agents.errors import RunnerError

        await self.client.initialize()
        await self.client.open()
        release = asyncio.Event()

        async def pending(**kwargs):
            await release.wait()
            return SimpleNamespace(stop_reason="cancelled", usage=None)

        self.connection.prompt = AsyncMock(side_effect=pending)
        self.connection.cancel.side_effect = lambda **kwargs: release.set()
        with self.assertRaisesRegex(RunnerError, "executor_lost"):
            await self.client.prompt(
                "task",
                cancelled=threading.Event(),
                seconds=1,
                check_health=Mock(side_effect=RunnerError("executor_lost")),
            )
        self.connection.cancel.assert_awaited_once_with(session_id="native-session")
        self.container.close.assert_not_called()  # The lifecycle owner still closes it.

    async def test_host_policy_metadata_is_sent_without_becoming_prompt_text(self):
        await self.client.initialize()
        await self.client.open()
        self.connection.prompt = AsyncMock(
            return_value=SimpleNamespace(stop_reason="end_turn", usage=None)
        )
        await self.client.prompt(
            "task",
            cancelled=threading.Event(),
            seconds=1,
            metadata={"laomedo": {"skills": []}},
        )
        arguments = self.connection.prompt.call_args.kwargs
        self.assertEqual(arguments["laomedo"], {"skills": []})
        self.assertEqual(arguments["prompt"][0].text, "task")

    async def test_commentary_is_not_part_of_final_payload(self):
        self.client.updates = [
            {
                "sessionUpdate": "agent_message_chunk",
                "messageId": "commentary",
                "content": {"type": "text", "text": "I will inspect it."},
            },
            {"sessionUpdate": "tool_call", "toolCallId": "call"},
            {
                "sessionUpdate": "agent_message_chunk",
                "messageId": "answer",
                "content": {"type": "text", "text": '{"result":'},
            },
            {
                "sessionUpdate": "agent_message_chunk",
                "messageId": "answer",
                "content": {"type": "text", "text": "true}"},
            },
        ]
        self.assertEqual(self.client._answer(), '{"result":true}')


@unittest.skipIf(AcpSession is None, "Optional runner ACP dependency is not installed")
class AcpOrderingTests(unittest.IsolatedAsyncioTestCase):
    """Pin actual SDK notification ordering with an internal in-memory wire."""

    async def test_raw_terminal_notification_is_captured_before_prompt_returns(self):
        class Wire:
            def __init__(self):
                self.messages = queue.Queue()

            def write(self, payload):
                request = json.loads(payload)
                method = request["method"]
                if method == "initialize":
                    result = {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}}
                elif method == "session/new":
                    result = {"sessionId": "native-session"}
                elif method == "session/prompt":
                    self.messages.put(SimpleNamespace(channel="stdout", data=json.dumps({"method": "_laomedo/codexEvent", "params": {"method": "turn/completed", "params": {"threadId": "native-session", "turn": {"id": "actual-native-turn", "status": "completed"}}}}).encode()))
                    result = {"stopReason": "end_turn"}
                else:
                    raise AssertionError(method)
                self.messages.put(SimpleNamespace(channel="stdout", data=json.dumps({"id": request["id"], "result": result}).encode()))

            def read_line(self):
                return self.messages.get(timeout=5)

            def close(self):
                self.messages.put(None)

        observed = []
        client = AcpSession(Wire(), on_extension=lambda method, params: observed.append(params))
        try:
            await client.initialize()
            await client.open()
            await client.prompt("test prompt", cancelled=threading.Event(), seconds=1)
            self.assertEqual(observed[0]["params"]["turn"]["id"], "actual-native-turn")
        finally:
            await client.close()


@unittest.skipIf(AcpSession is None, "Optional runner ACP dependency is not installed")
class DockerTransportTests(unittest.IsolatedAsyncioTestCase):
    """Exercise framing and refusal without fabricating provider acceptance."""

    async def test_stderr_cannot_become_a_protocol_response(self):
        session = Mock()
        session.read_line.side_effect = [
            SimpleNamespace(channel="stderr", data=b"private diagnostic"),
            SimpleNamespace(channel="stdout", data=b'{"result":{}}\n'),
        ]
        self.assertEqual(await DockerTransport(session).receive(), {"result": {}})

    async def test_malformed_stdout_and_nonobjects_are_refused(self):
        for data in [b"not json", b"[]", b"null"]:
            session = Mock()
            session.read_line.return_value = SimpleNamespace(
                channel="stdout", data=data
            )
            failed = Mock()
            with self.assertNoLogs():
                self.assertIsNone(
                    await DockerTransport(session, on_failure=failed).receive()
                )
            failed.assert_called_once_with()

    async def test_sdk_bound_malformed_updates_disconnect_without_logging_input(self):
        for message in (
            {
                "method": "session/update",
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": {"secret": "private"}},
                    },
                },
            },
            {"method": "unknown-notification", "params": {"private": "payload"}},
            {"id": [], "result": {}},
            {"method": "_claude/sdkMessage", "params": "private"},
        ):
            session = Mock()
            session.read_line.return_value = SimpleNamespace(
                channel="stdout", data=json.dumps(message).encode()
            )
            failed = Mock()
            with self.assertNoLogs():
                self.assertIsNone(
                    await DockerTransport(session, on_failure=failed).receive()
                )
            failed.assert_called_once_with()

    async def test_eof_is_not_claimed_as_success(self):
        session = Mock()
        session.read_line.return_value = None
        self.assertIsNone(await DockerTransport(session).receive())
        session.wait.assert_not_called()
        session.close.assert_not_called()

    async def test_write_uses_sdk_message_and_does_not_start_a_subprocess(self):
        session = Mock()
        await DockerTransport(session).send(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        self.assertEqual(
            json.loads(session.write.call_args.args[0]),
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
