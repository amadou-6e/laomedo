"""Internal protocol tests, not live Codex acceptance."""
import unittest
from unittest.mock import Mock
from laomedo.local_runner import _advertised_models, RunnerError

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
