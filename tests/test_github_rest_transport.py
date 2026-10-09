"""No-network tests of the narrow credential-owning REST adapter."""

import io
import json
import unittest
from urllib import error

from laomedo.github_mediation import KnownRejected
from laomedo.github_rest_transport import GitHubRestTransport


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class _Opener:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.responses = []

    def open(self, call, timeout):
        self.calls.append((call, timeout))
        if self.failure:
            raise self.failure
        return _Response(self.responses.pop(0) if self.responses else
                         b'{"number":7,"state":"open"}')


class GitHubRestTransportTests(unittest.TestCase):
    def setUp(self):
        self.opener = _Opener()
        self.adapter = GitHubRestTransport(
            "example/disposable", lambda: "synthetic-secret", opener=self.opener)

    def test_pr_create_is_bound_and_keeps_token_out_of_url_or_body(self):
        payload = {"title": "Test", "body": "marker-1", "head": "branch-a",
                   "base": "main", "marker": "marker-1"}
        result = self.adapter("example/disposable", "pr_create", payload)
        self.assertEqual(result["number"], 7)
        call, timeout = self.opener.calls[0]
        self.assertEqual(call.get_method(), "POST")
        self.assertEqual(call.full_url, "https://api.github.com/repos/example/disposable/pulls")
        self.assertEqual(timeout, 15)
        self.assertEqual(json.loads(call.data)["body"], "marker-1")
        self.assertNotIn("synthetic-secret", call.full_url + call.data.decode())
        self.assertEqual(call.get_header("Authorization"), "Bearer synthetic-secret")

    def test_changed_repository_or_missing_marker_never_reaches_provider(self):
        with self.assertRaisesRegex(KnownRejected, "repository_denied"):
            self.adapter("other/repo", "actions_read", {"job_id": 1})
        with self.assertRaisesRegex(KnownRejected, "pr_payload_invalid"):
            self.adapter("example/disposable", "pr_create", {
                "title": "x", "body": "no marker", "head": "b", "base": "main",
                "marker": "required"})
        self.assertEqual(self.opener.calls, [])

    def test_actions_and_repository_scoped_read_only(self):
        self.adapter("example/disposable", "actions_read", {"job_id": 12})
        self.adapter("example/disposable", "actions_read", {"resource": "runs"})
        self.adapter("example/disposable", "api_rest_read", {
            "path": "/repos/example/disposable/issues/1"})
        self.assertEqual([call.full_url for call, _ in self.opener.calls], [
            "https://api.github.com/repos/example/disposable/actions/jobs/12",
            "https://api.github.com/repos/example/disposable/actions/runs",
            "https://api.github.com/repos/example/disposable/issues/1"])
        with self.assertRaisesRegex(KnownRejected, "actions_target_invalid"):
            self.adapter("example/disposable", "actions_read", {"resource": "other"})
        for path in ("/repos/other/repo/issues/1", "/repos/example/disposable/../other",
                     "/repos/example/disposable/%2e%2e/other"):
            with self.assertRaisesRegex(KnownRejected, "api_path_denied"):
                self.adapter("example/disposable", "api_rest_read", {"path": path})
        self.assertEqual(len(self.opener.calls), 3)

    def test_unsupported_writes_fail_without_ambient_gh_fallback(self):
        for operation in ("git_push", "api_rest_write", "api_graphql_mutation"):
            with self.assertRaisesRegex(KnownRejected, "operation_not_implemented"):
                self.adapter("example/disposable", operation, {})
        with self.assertRaisesRegex(ValueError, "credential_supplier_required"):
            GitHubRestTransport("example/disposable", None)
        self.assertEqual(self.opener.calls, [])

    def test_pr_update_checks_real_head_before_patch(self):
        payload = {"number": 7, "title": "Changed", "head": "branch-a",
                   "base": "main", "marker": "marker-1",
                   "expected": {"title": "Old", "body": "Old body",
                                "head_sha": "a" * 40}}
        with self.assertRaisesRegex(KnownRejected, "pr_target_denied"):
            self.adapter("example/disposable", "pr_update", payload)
        self.assertEqual([call.get_method() for call, _ in self.opener.calls], ["GET"])
        self.opener.calls.clear()
        existing = {"number": 7, "title": "Old", "body": "Old body",
            "head": {"ref": "branch-a", "sha": "a" * 40,
            "repo": {"full_name": "example/disposable"}},
            "base": {"ref": "main"}}
        updated = dict(existing, title="Changed")
        self.opener.responses = [json.dumps(item).encode()
                                 for item in (existing, updated, updated)]
        self.adapter("example/disposable", "pr_update", payload)
        self.assertEqual([call.get_method() for call, _ in self.opener.calls], ["GET", "PATCH", "GET"])

    def test_pr_update_refuses_stale_snapshot_without_patch(self):
        existing = {"number": 7, "title": "Human edit", "body": "Old body",
                    "head": {"ref": "branch-a", "sha": "a" * 40,
                             "repo": {"full_name": "example/disposable"}},
                    "base": {"ref": "main"}}
        self.opener.responses = [json.dumps(existing).encode()]
        with self.assertRaisesRegex(KnownRejected, "pr_snapshot_changed"):
            self.adapter("example/disposable", "pr_update", {
                "number": 7, "title": "Changed", "head": "branch-a",
                "base": "main", "marker": "m",
                "expected": {"title": "Old", "body": "Old body",
                             "head_sha": "a" * 40}})
        self.assertEqual([c.get_method() for c, _ in self.opener.calls], ["GET"])

    def test_pr_update_readback_mismatch_is_unknown_not_rejected(self):
        existing = {"number": 7, "title": "Old", "body": "Old body",
                    "head": {"ref": "branch-a", "sha": "a" * 40,
                             "repo": {"full_name": "example/disposable"}},
                    "base": {"ref": "main"}}
        self.opener.responses = [json.dumps(existing).encode()] * 3
        with self.assertRaisesRegex(ValueError, "pr_update_readback_unknown"):
            self.adapter("example/disposable", "pr_update", {
                "number": 7, "title": "Changed", "head": "branch-a",
                "base": "main", "marker": "m",
                "expected": {"title": "Old", "body": "Old body",
                             "head_sha": "a" * 40}})
        self.assertEqual([c.get_method() for c, _ in self.opener.calls],
                         ["GET", "PATCH", "GET"])

    def test_pr_read_returns_normalized_bound_readback(self):
        self.opener.responses = [json.dumps({"number": 7, "title": "Ready",
            "body": "Reviewed body", "state": "open",
            "head": {"ref": "branch-a", "sha": "a" * 40,
                     "repo": {"full_name": "example/disposable"}},
            "base": {"ref": "main"}}).encode()]
        result = self.adapter("example/disposable", "pr_read", {"number": 7})
        self.assertEqual(result["body"], "Reviewed body")
        self.assertEqual(result["head"]["sha"], "a" * 40)
        self.assertEqual(self.opener.calls[0][0].get_method(), "GET")
        self.assertEqual(self.opener.calls[0][0].full_url,
                         "https://api.github.com/repos/example/disposable/pulls/7")
        with self.assertRaisesRegex(KnownRejected, "pr_read_target_invalid"):
            self.adapter("example/disposable", "pr_read", {"number": 7, "path": "evil"})

    def test_complete_rejection_and_ambiguous_error_are_distinct(self):
        self.opener.failure = error.HTTPError("https://api.github.com", 403,
                                               "Forbidden", None, None)
        with self.assertRaisesRegex(KnownRejected, "github_http_403"):
            self.adapter("example/disposable", "actions_read", {"job_id": 1})
        self.opener.failure = error.HTTPError("https://api.github.com", 500,
                                               "Server error", None, None)
        with self.assertRaises(error.HTTPError):
            self.adapter("example/disposable", "actions_read", {"job_id": 1})

    def test_bound_connection_requires_context_aware_token_supplier(self):
        with self.assertRaisesRegex(KnownRejected, "provider_credential_unavailable"):
            self.adapter("example/disposable", "actions_read", {"job_id": 1},
                         connection_id="connection-a", connection_generation=2)
        self.assertEqual(self.opener.calls, [])
        seen = []

        def selected_token(connection_id, generation):
            seen.append((connection_id, generation))
            if (connection_id, generation) != ("connection-a", 2):
                raise KeyError("not current")
            return "synthetic-selected-secret"

        adapter = GitHubRestTransport("example/disposable", selected_token,
                                     opener=self.opener)
        adapter("example/disposable", "actions_read", {"job_id": 1},
                connection_id="connection-a", connection_generation=2)
        self.assertEqual(seen, [("connection-a", 2)])
        self.assertEqual(self.opener.calls[0][0].get_header("Authorization"),
                         "Bearer synthetic-selected-secret")
        with self.assertRaisesRegex(KnownRejected, "provider_credential_unavailable"):
            adapter("example/disposable", "actions_read", {"job_id": 1},
                    connection_id="connection-a", connection_generation=1)
        self.assertEqual(len(self.opener.calls), 1)


if __name__ == "__main__":
    unittest.main()
