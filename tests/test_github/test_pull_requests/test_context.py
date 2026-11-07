"""Internal controls for the unified PR handoff; no live mutations or model turns."""

import tempfile
import unittest
from laomedo.github.pull_requests.context import context_value, task_text
from test_github.test_pull_requests.utils import create_case


class PRContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)
        self.result = self.case.gateway.execute(self.case.url, [], "open", 1)

    def test_successful_result_is_identity_and_task_not_a_replayed_operation(self):
        for status in ("not_requested", "succeeded"):
            value = {
                **self.result,
                "operation": {"status": status, "error_category": None},
            }
            context = context_value(value)
            self.assertEqual(context.pr.number, 1)
            self.assertIn("https://github.com/owner/repo/pull/1", task_text(value))
            self.assertNotIn("grant_ref", task_text(value))

    def test_failed_and_uncertain_snapshots_cannot_become_tasks_or_reads(self):
        for status in ("failed", "unknown"):
            value = {
                **self.result,
                "operation": {
                    "status": status,
                    "error_category": "private-provider-text",
                },
            }
            for decoder in (context_value, task_text):
                with self.assertRaisesRegex(ValueError, "pr_context_upstream_failed"):
                    decoder(value)

    def test_malformed_and_unauthorized_operations_are_not_coerced(self):
        for value in (
            {},
            {"pr": {"repository": "owner/repo", "number": True}},
            {"pr": {"repository": "owner/repo", "number": 0}},
            {"action": "close"},
            {"action": "merge"},
            {**self.result, "grant_ref": "untrusted"},
            "not-json",
        ):
            with self.assertRaisesRegex(ValueError, "pr_context_invalid"):
                context_value(value)
        with self.assertRaisesRegex(ValueError, "pr_context_invalid"):
            task_text({"pr": {"repository": "owner/repo", "number": 1}})

    def test_normal_operation_requires_explicit_host_grant_and_request_identity(self):
        value = context_value(
            {
                "pr": {"repository": "owner/repo", "number": 1},
                "operation": {
                    "action": "modify",
                    "request_id": "once",
                    "grant_ref": "host-ref",
                    "changes": {"title": "Changed"},
                },
            }
        )
        self.assertEqual(value.operation.request_id, "once")
        self.assertEqual(self.case.provider.writes, [])
