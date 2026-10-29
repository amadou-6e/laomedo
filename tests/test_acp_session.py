"""Internal protocol controls; these do not establish live provider acceptance."""

import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

try:
    from acp import RequestError
    from laomedo.agents.protocol.acp.session import AcpSession
    from laomedo.agents.protocol.acp.transport import DockerTransport
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
            "laomedo.agents.protocol.acp.session.connect_to_agent",
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
            with self.assertRaisesRegex(ValueError, "^runner_transport_failed$"):
                await DockerTransport(session).receive()

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
