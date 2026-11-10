"""Internal protocol tests, not live Codex acceptance."""

import asyncio
import unittest
from unittest.mock import Mock, AsyncMock
from laomedo.agents.agents.codex.runtime import CodexAgentRuntime
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor


class CatalogTests(unittest.TestCase):
    def test_native_labels_and_defaults_survive_the_python_boundary(self):
        server = Mock(
            extension=AsyncMock(
                return_value={
                    "data": [
                        {
                            "id": "reported",
                            "displayName": "Native label",
                            "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
                            "defaultReasoningEffort": "low",
                            "isDefault": True,
                        }
                    ]
                }
            )
        )
        from laomedo.agents.agents.base.models import ModelCatalog

        models = asyncio.run(CodexAgentRuntime.models(server))
        catalog = ModelCatalog.from_payload(
            {"models": models, "default_model_id": "reported", "submitted_turns": 0}
        )
        self.assertEqual(catalog.models[0].display_name, "Native label")
        self.assertEqual(catalog.models[0].default_reasoning_effort, "low")
        self.assertEqual(catalog.default_model_id, "reported")
        self.assertEqual(
            catalog.to_payload(provider="codex"),
            {
                "models": [{"id": "reported", "efforts": ["low"]}],
                "submitted_turns": 0,
            },
        )

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
            asyncio.run(CodexAgentRuntime.models(server)),
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
            asyncio.run(CodexAgentRuntime.models(server))

    def test_duplicate_ids_are_rejected(self):
        server = Mock(extension=AsyncMock())
        entry = {"id": "duplicate", "supportedReasoningEfforts": ["low"]}
        server.extension.return_value = {"data": [entry, entry]}
        with self.assertRaisesRegex(RunnerError, "model_list_invalid_entry"):
            asyncio.run(CodexAgentRuntime.models(server))

    def test_invalid_reported_defaults_preserve_native_error_category(self):
        for extra in (
            {"defaultReasoningEffort": "not-supported"},
            {"isDefault": "true"},
            {"displayName": ""},
        ):
            with self.subTest(extra=extra):
                server = Mock(
                    extension=AsyncMock(
                        return_value={
                            "data": [
                                {
                                    "id": "reported",
                                    "supportedReasoningEfforts": ["low"],
                                    **extra,
                                }
                            ]
                        }
                    )
                )
                with self.assertRaisesRegex(RunnerError, "model_list_invalid_entry"):
                    asyncio.run(CodexAgentRuntime.models(server))

    def test_two_reported_default_models_are_rejected_before_caching(self):
        with TemporaryDirectory() as directory:
            runner = LocalRunner.__new__(LocalRunner)
            runner.state = Path(directory)
            runner.auth = None
            runner.split_executor = False
            runner._open_server = Mock(
                return_value=Mock(
                    initialize=AsyncMock(),
                    close=AsyncMock(),
                    models=AsyncMock(
                        return_value=[
                            {"id": "one", "efforts": ["low"], "is_default": True},
                            {"id": "two", "efforts": ["low"], "is_default": True},
                        ]
                    ),
                )
            )
            with self.assertRaisesRegex(RunnerError, "model_list_invalid_entry"):
                runner.catalog.list_models()
            self.assertIsNone(runner.catalog.snapshot())

    def test_unique_endless_cursors_are_bounded(self):
        server = Mock(extension=AsyncMock())
        server.extension.side_effect = [
            {"data": [], "nextCursor": str(i)} for i in range(50)
        ]
        with self.assertRaisesRegex(RunnerError, "model_list_page_limit"):
            asyncio.run(CodexAgentRuntime.models(server))

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
