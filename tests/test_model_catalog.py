"""Internal protocol tests, not live Codex acceptance."""

import asyncio
import unittest
from unittest.mock import Mock, AsyncMock
from laomedo.agents.agents.codex.controller.service import CodexController
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor


class CatalogTests(unittest.TestCase):
    def test_pagination_and_dynamic_efforts(self):
        server = Mock(extension=AsyncMock())
        server.extension.side_effect = [
            {
                "data": [
                    {
                        "id": "one",
                        "supportedReasoningEfforts": [{"reasoningEffort": "novel"}],
                    }
                ],
                "nextCursor": "page2",
            },
            {"data": [{"id": "two", "supportedReasoningEfforts": ["different"]}]},
        ]
        self.assertEqual(
            asyncio.run(CodexController.models(server)),
            [
                {"id": "one", "efforts": ["novel"]},
                {"id": "two", "efforts": ["different"]},
            ],
        )
        self.assertEqual(
            server.extension.call_args.args,
            ("laomedo/codexModels", {"cursor": "page2"}),
        )
        self.assertTrue(
            all(
                call.args[0] == "laomedo/codexModels"
                for call in server.extension.call_args_list
            )
        )

    def test_repeated_cursor_fails(self):
        server = Mock(extension=AsyncMock())
        server.extension.return_value = {"data": [], "nextCursor": "same"}
        with self.assertRaisesRegex(RunnerError, "model_list_invalid_cursor"):
            asyncio.run(CodexController.models(server))

    def test_duplicate_ids_are_rejected(self):
        server = Mock(extension=AsyncMock())
        entry = {"id": "duplicate", "supportedReasoningEfforts": ["low"]}
        server.extension.return_value = {"data": [entry, entry]}
        with self.assertRaisesRegex(RunnerError, "model_list_invalid_entry"):
            asyncio.run(CodexController.models(server))

    def test_unique_endless_cursors_are_bounded(self):
        server = Mock(extension=AsyncMock())
        server.extension.side_effect = [
            {"data": [], "nextCursor": str(i)} for i in range(50)
        ]
        with self.assertRaisesRegex(RunnerError, "model_list_page_limit"):
            asyncio.run(CodexController.models(server))

    def test_concurrent_discovery_is_cached_and_temporary_state_removed(self):
        with TemporaryDirectory() as directory:
            runner = LocalRunner.__new__(LocalRunner)
            runner.state = Path(directory)
            runner.auth = None
            runner.split_executor = False
            server = Mock(
                initialize=AsyncMock(),
                models=AsyncMock(
                    return_value=[{"id": "runtime", "efforts": ["new-effort"]}]
                ),
                close=AsyncMock(),
            )
            runner._open_server = Mock(return_value=server)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: runner.model_catalog(), range(4)))
            self.assertTrue(all(result == results[0] for result in results))
            self.assertEqual(runner._open_server.call_count, 1)
            server.close.assert_called_once()
            self.assertEqual(list((runner.state / "catalog").iterdir()), [])
