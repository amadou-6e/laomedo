"""No-model host dispatch identity controls for the prospective live graph."""
import unittest
from unittest.mock import patch
from experiments.exp139.bindings import BoundRunner, request_digest
from laomedo.local_runner import LocalRunner, RunnerError


class BindingTests(unittest.TestCase):
    def make_runner(self, request, case="success"):
        calls = []
        with patch.object(LocalRunner, "__init__", return_value=None):
            runner = BoundRunner(approved_requests={request_digest(request): case},
                authorization_factory=lambda: calls.append("issued") or "fixture-reference")
        return runner, calls

    def test_host_selects_grant_but_preserves_graph_request_hash(self):
        original = {"task": "frozen task", "model": "fixture"}
        runner, calls = self.make_runner(original)
        expected = request_digest(original)
        with patch.object(LocalRunner, "_prepare", return_value={}) as prepare:
            runner._prepare(original, request_hash=expected)
            self.assertEqual(prepare.call_args.kwargs["request_hash"], expected)
            self.assertEqual(prepare.call_args.args[0]["github_authorization_ref"], "fixture-reference")
        self.assertNotIn("github_authorization_ref", original)
        self.assertEqual(calls, ["issued"])

    def test_modified_or_graph_supplied_scope_and_duplicate_refuse(self):
        original = {"task": "frozen task"}
        runner, calls = self.make_runner(original)
        for request in ({"task": "changed"}, {**original, "github_authorization_ref": "injected"}):
            with self.assertRaisesRegex(RunnerError, "experiment_request_binding_denied"):
                runner._prepare(request)
        with patch.object(LocalRunner, "_prepare", side_effect=RunnerError("setup_failed")):
            with self.assertRaises(RunnerError):
                runner._prepare(original)
        with self.assertRaisesRegex(RunnerError, "experiment_request_binding_denied"):
            runner._prepare(original)
        self.assertEqual(calls, ["issued"])

    def test_failure_case_has_no_git_authorization(self):
        original = {"task": "failure fixture"}
        runner, calls = self.make_runner(original, "failure")
        with patch.object(LocalRunner, "_prepare", return_value={}) as prepare:
            runner._prepare(original)
            self.assertNotIn("github_authorization_ref", prepare.call_args.args[0])
        self.assertEqual(calls, [])
