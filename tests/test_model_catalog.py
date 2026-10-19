"""Internal protocol tests, not live Codex acceptance."""
import unittest
from unittest.mock import Mock
from laomedo.local_runner import _advertised_models, RunnerError, LocalRunner
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor

class CatalogTests(unittest.TestCase):
    def test_pagination_and_dynamic_efforts(self):
        server = Mock()
        server.request.side_effect = [
            {"result": {"data": [{"id": "one", "supportedReasoningEfforts": [{"reasoningEffort": "novel"}]}], "nextCursor": "page2"}},
            {"result": {"data": [{"id": "two", "supportedReasoningEfforts": ["different"]}]}}]
        self.assertEqual(_advertised_models(server), [{"id": "one", "efforts": ["novel"]}, {"id": "two", "efforts": ["different"]}])
        self.assertEqual(server.request.call_args.args, ("model/list", {"cursor": "page2"}))
        self.assertTrue(all(call.args[0] == "model/list" for call in server.request.call_args_list))

    def test_repeated_cursor_fails(self):
        server = Mock()
        server.request.return_value = {"result": {"data": [], "nextCursor": "same"}}
        with self.assertRaisesRegex(RunnerError, "model_list_invalid_cursor"):
            _advertised_models(server)

    def test_duplicate_ids_are_rejected(self):
        server = Mock()
        entry = {"id": "duplicate", "supportedReasoningEfforts": ["low"]}
        server.request.return_value = {"result": {"data": [entry, entry]}}
        with self.assertRaisesRegex(RunnerError, "model_list_invalid_entry"):
            _advertised_models(server)

    def test_unique_endless_cursors_are_bounded(self):
        server = Mock()
        server.request.side_effect = [{"result": {"data": [], "nextCursor": str(i)}} for i in range(50)]
        with self.assertRaisesRegex(RunnerError, "model_list_page_limit"):
            _advertised_models(server)

    def test_concurrent_discovery_is_cached_and_temporary_state_removed(self):
        with TemporaryDirectory() as directory:
            runner = LocalRunner.__new__(LocalRunner)
            runner.state = Path(directory)
            runner.auth = None
            runner.split_executor = False
            server = Mock()
            server.request.side_effect = [{"result": {}}, {"result": {"data": [{"id": "runtime", "supportedReasoningEfforts": ["new-effort"]}]}}]
            runner._open_server = Mock(return_value=server)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: runner.model_catalog(), range(4)))
            self.assertTrue(all(result == results[0] for result in results))
            self.assertEqual(runner._open_server.call_count, 1)
            server.close.assert_called_once()
            self.assertEqual(list((runner.state / "catalog").iterdir()), [])
