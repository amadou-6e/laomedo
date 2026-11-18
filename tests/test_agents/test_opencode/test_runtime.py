"""Native selector guards; fixtures do not establish live model acceptance."""

import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime
from laomedo.agents.agents.opencode.settings import CLI_VERSION
from laomedo.agents.errors import RunnerError


class OpenCodeRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Refuse stale catalogue selections before native configuration or prompting."""

    async def test_retired_model_is_not_sent_to_native_selector(self):
        backend = object.__new__(OpenCodeAgentRuntime)
        backend.session = Mock()
        client = Mock()
        client.initialize = AsyncMock(
            return_value=SimpleNamespace(
                agent_info=SimpleNamespace(version=CLI_VERSION),
            )
        )
        picker = SimpleNamespace(
            category="model",
            id="model",
            options=[
                SimpleNamespace(options=[SimpleNamespace(value="opencode-go/current")]),
            ],
        )
        client.open = AsyncMock(return_value=SimpleNamespace(config_options=[picker]))
        client.configure = AsyncMock()
        client.close = AsyncMock()
        capture = Mock()
        with patch(
            "laomedo.agents.agents.base.acp.session.AcpSession", return_value=client
        ):
            with self.assertRaisesRegex(RunnerError, "^opencode_model_not_connected$"):
                await backend._run_acp(
                    "unused",
                    "opencode-go/retired",
                    None,
                    threading.Event(),
                    capture,
                    Mock(),
                )
        client.configure.assert_not_called()
        client.prompt.assert_not_called()
        capture.begin.assert_not_called()
        client.close.assert_awaited_once()
