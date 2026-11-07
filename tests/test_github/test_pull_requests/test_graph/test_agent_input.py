"""Actual Agent adapter preparation with internal PR snapshots, no runner calls."""

import unittest
from importlib.util import find_spec

if find_spec("lfx") is None:
    raise unittest.SkipTest("Optional lfx runtime is not installed")

import tempfile
from unittest.mock import patch
from lfx.schema import Data, Message
from test_langflow.test_codex_component import component
from test_github.test_pull_requests.utils import create_case


class PRAgentInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)
        self.result = self.case.gateway.execute(self.case.url, [], "open", 1)

    def test_successful_context_becomes_text_in_real_agent_request(self):
        node = component(task=Data(data=self.result))
        body = node._prepare_request()[1]
        self.assertIn("PR: https://github.com/owner/repo/pull/1", body["task"])
        self.assertIn("Current PR body", body["task"])
        self.assertNotIn("grant_ref", body["task"])

    def test_failed_and_unknown_context_refuse_before_http_dispatch(self):
        for status in ("failed", "unknown"):
            result = {
                **self.result,
                "operation": {"status": status, "error_category": "dummy"},
            }
            node = component(task=Data(data=result))
            with patch(
                "laomedo.integrations.langflow.agent.component._HTTP.open"
            ) as transport:
                with self.assertRaisesRegex(ValueError, "pr_context_upstream_failed"):
                    node._prepare_request()
                transport.assert_not_called()

    def test_ordinary_text_and_message_task_behavior_stays_unchanged(self):
        for value in ("Existing task", Message(text="Existing task")):
            self.assertEqual(
                component(task=value)._prepare_request()[1]["task"], "Existing task"
            )
