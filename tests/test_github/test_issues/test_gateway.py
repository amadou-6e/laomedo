"""Gateway regression controls with internal provider doubles."""

import json
from pathlib import Path
import tempfile
import unittest
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.host.mediation.errors import MediationError

from test_github.test_issues.utils import create_case


class LiveGitHubIssueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)

    def execute(self, action="close", changes=None, request_id="effect"):
        op = {"action": action, "request_id": request_id, "grant_ref": "grant"}
        if changes is not None:
            op["changes"] = changes
        return self.case.gateway.execute(self.case.url, [], "open", 1, op)

    def test_all_labels_filter_and_pr_exclusion(self):
        result = self.case.gateway.discover(self.case.url, ["research", "backend"])
        self.assertEqual([v["number"] for v in result["issues"]], [1])
        self.assertEqual(
            len(self.case.gateway.discover(self.case.url, [])["issues"]), 3
        )

    def test_fresh_read_and_changed_filter_refusal(self):
        self.case.provider.issues[1]["body"] = "Changed on GitHub"
        self.assertEqual(
            self.case.gateway.execute(self.case.url, [], "open", 1)["issue"]["body"],
            "Changed on GitHub",
        )
        with self.assertRaisesRegex(ValueError, "no_longer_matches"):
            self.case.gateway.execute(self.case.url, ["backend"], "open", 2)

    def test_close_and_restart_replay_send_one_patch(self):
        result = self.execute()
        self.assertEqual(result["operation"]["status"], "succeeded")
        self.assertEqual(result["issue"]["state"], "closed")
        restarted = GitHubIssueGateway(
            {"owner/repo": self.case.transport},
            self.case.store,
            lambda _: self.case.binding,
        )
        self.assertEqual(
            restarted.execute(
                self.case.url,
                [],
                "open",
                1,
                {"action": "close", "request_id": "effect", "grant_ref": "grant"},
            ),
            result,
        )
        self.assertEqual(self.case.provider.patch_count, 1)

    def test_modify_title_body_and_labels(self):
        result = self.execute(
            "modify", {"title": "Changed", "body": "", "labels": ["research"]}
        )
        self.assertEqual(result["operation"]["status"], "succeeded")
        self.assertEqual(result["issue"]["title"], "Changed")
        self.assertEqual(result["issue"]["body"], "")
        self.assertEqual(result["issue"]["labels"], ["research"])

    def test_timeout_after_effect_stays_unknown_and_never_repeats(self):
        self.case.provider.timeout_after_write = True
        first = self.execute()
        self.assertEqual(first["operation"]["status"], "unknown")
        self.assertEqual(self.execute(), first)
        self.assertEqual(self.case.provider.patch_count, 1)
        self.assertNotIn("dummy-provider-secret", json.dumps(first))
        second = self.case.gateway.execute(
            self.case.url,
            [],
            "all",
            1,
            {"action": "close", "request_id": "new-effect", "grant_ref": "grant"},
        )
        self.assertEqual(second["operation"]["status"], "failed")
        self.assertEqual(self.case.provider.patch_count, 1)

    def test_known_rejection_and_payload_identity(self):
        self.case.provider.reject_patch = True
        self.assertEqual(self.execute()["operation"]["status"], "failed")
        with self.assertRaisesRegex(ValueError, "operation_conflict"):
            self.execute("modify", {"title": "Other"})
        self.assertEqual(self.case.provider.patch_count, 1)

    def test_expiry_revocation_and_foreign_target(self):
        self.case.clock[0] = 200
        self.assertEqual(
            self.execute()["operation"]["error_category"], "grant_unavailable"
        )
        self.case.clock[0] = 100
        self.case.store.revoke_run("run")
        self.assertEqual(
            self.execute(request_id="next")["operation"]["status"], "failed"
        )
        self.assertEqual(self.case.provider.patch_count, 0)

    def test_grant_requires_explicit_issue_targets(self):
        with self.assertRaises(MediationError):
            self.case.store.issue(
                run_id="other",
                invocation_id="other",
                repository="owner/repo",
                operations={"issue_update"},
                ttl_seconds=60,
            )
        result = self.case.gateway.execute(
            self.case.url,
            [],
            "open",
            2,
            {"action": "close", "request_id": "wrong", "grant_ref": "grant"},
        )
        self.assertEqual(result["operation"]["error_category"], "issue_target_denied")
        self.assertEqual(self.case.provider.patch_count, 0)

    def test_arbitrary_operation_targets_or_fields_are_refused(self):
        for op in (
            {"action": "close", "request_id": "x", "grant_ref": "grant", "number": 2},
            {
                "action": "modify",
                "request_id": "x",
                "grant_ref": "grant",
                "changes": {"assignee": "someone"},
            },
        ):
            with self.assertRaises(ValueError):
                self.case.gateway.execute(self.case.url, [], "open", 1, op)
        self.assertEqual(self.case.provider.patch_count, 0)

    def test_incomplete_pagination_is_not_empty_success(self):
        self.case.provider.full_pages = True
        with self.assertRaisesRegex(ValueError, "discovery_incomplete"):
            self.case.gateway.discover(self.case.url, [])

    def test_concurrent_duplicate_returns_unknown_then_confirmed_without_redispatch(
        self,
    ):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        entered, release = threading.Event(), threading.Event()
        original = self.case.provider.open

        def blocked(call, timeout=15):
            if call.get_method() == "PATCH":
                entered.set()
                if not release.wait(5):
                    raise TimeoutError()
            return original(call, timeout)

        self.case.provider.open = blocked
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.execute)
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.execute)
            duplicate = second.result(timeout=3)
            self.assertEqual(duplicate["operation"]["status"], "unknown")
            release.set()
            self.assertEqual(
                first.result(timeout=3)["operation"]["status"], "succeeded"
            )
        self.assertEqual(self.execute()["operation"]["status"], "succeeded")
        self.assertEqual(self.case.provider.patch_count, 1)

    def test_loopback_service_auth_and_error_redaction(self):
        import threading
        from urllib import request
        from urllib import error
        from laomedo.github.interface.issues.server import IssueServer as server

        token = "dummy-control-" + "x" * 40
        service = server(self.case.gateway, token, port=0)
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        url = f"http://127.0.0.1:{service.server_address[1]}/v1/github-issues/discover"
        payload = json.dumps(
            {"repository_url": self.case.url, "labels": [], "state": "open"}
        ).encode()
        with self.assertRaises(error.HTTPError) as rejected:
            request.urlopen(
                request.Request(
                    url, data=payload, headers={"Content-Type": "application/json"}
                )
            )
        self.assertEqual(rejected.exception.code, 401)
        rejected.exception.close()
        call = request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        data = json.load(request.urlopen(call))
        self.assertEqual(len(data["issues"]), 3)
        self.assertNotIn("DUMMY-PROVIDER", json.dumps(data))

    def test_revocation_during_read_refuses_before_patch(self):
        original = self.case.provider.open
        reads = [0]

        def revoke_on_read(call, timeout=15):
            if call.get_method() == "GET" and call.full_url.endswith("/issues/1"):
                reads[0] += 1
                if reads[0] == 2:
                    self.case.store.revoke_run("run")
            return original(call, timeout)

        self.case.provider.open = revoke_on_read
        result = self.execute("modify", {"title": "Should not change"})
        self.assertEqual(result["operation"]["status"], "failed")
        self.assertEqual(self.case.provider.patch_count, 0)
        self.assertEqual(self.case.provider.issues[1]["title"], "Task 1")

    def test_rebinding_a_reference_cannot_reuse_another_runs_result(self):
        self.execute()
        _, replacement = self.case.store.issue(
            run_id="other-run",
            invocation_id="other-invoke",
            repository="owner/repo",
            operations={"issue_update"},
            target_issues={1},
            ttl_seconds=60,
        )
        self.case.binding = {
            "token": replacement,
            "run_id": "other-run",
            "repository": "owner/repo",
        }
        with self.assertRaisesRegex(ValueError, "issue_operation_conflict"):
            self.execute()
        self.assertEqual(self.case.provider.patch_count, 1)

    def test_rejected_readback_after_patch_stays_unknown(self):
        from urllib.error import HTTPError

        original = self.case.provider.open

        def fail_readback(call, timeout=15):
            if call.get_method() == "GET" and self.case.provider.patch_count:
                raise HTTPError(call.full_url, 403, "dummy-provider-secret", {}, None)
            return original(call, timeout)

        self.case.provider.open = fail_readback
        result = self.execute()
        self.assertEqual(result["operation"]["status"], "unknown")
        self.assertEqual(self.execute(), result)
        self.assertEqual(self.case.provider.patch_count, 1)

    def test_client_uncertain_delivery_and_bad_responses_are_not_rejections(self):
        import io
        from unittest.mock import patch
        from unittest.mock import MagicMock
        from urllib.error import HTTPError
        from laomedo.github.interface.issues.client import issue_request

        token_file = Path(self.temp.name) / "dummy-control-token"
        token_file.write_text("x" * 40, encoding="utf-8")
        env = {
            "LAOMEDO_GITHUB_ISSUE_URL": "http://127.0.0.1:8783",
            "LAOMEDO_GITHUB_ISSUE_TOKEN_FILE": str(token_file),
        }
        payload = dict(
            repository_url=self.case.url,
            labels=[],
            state="open",
            issue_number=1,
            operation={
                "action": "close",
                "request_id": "uncertain",
                "grant_ref": "grant",
            },
        )
        with (
            patch.dict("os.environ", env),
            patch(
                "laomedo.github.interface.issues.client.request.build_opener"
            ) as opener,
        ):
            for failure in (
                TimeoutError("dummy-secret"),
                ConnectionResetError(),
                HTTPError(
                    "http://127.0.0.1",
                    503,
                    "dummy-secret",
                    {},
                    io.BytesIO(b'{"error_category":"invalid_request"}'),
                ),
            ):
                opener.return_value.open.side_effect = failure
                with self.assertRaisesRegex(ValueError, "^issue_write_unknown$"):
                    issue_request("execute", **payload)
            opener.return_value.open.side_effect = None
            response = MagicMock()
            response.__enter__.return_value.read.return_value = b"[]"
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "^issue_write_unknown$"):
                issue_request("execute", **payload)
            opener.return_value.open.side_effect = HTTPError(
                "http://127.0.0.1",
                400,
                "",
                {},
                io.BytesIO(b'{"error_category":"issue_grant_unavailable"}'),
            )
            with self.assertRaisesRegex(ValueError, "^issue_grant_unavailable$"):
                issue_request("execute", **payload)

    def test_server_unexpected_write_exception_is_unknown_not_rejected(self):
        import threading
        from urllib import request
        from urllib import error
        from unittest.mock import patch
        from laomedo.github.interface.issues.server import IssueServer as server

        token = "x" * 40
        service = server(self.case.gateway, token, port=0)
        threading.Thread(target=service.serve_forever, daemon=True).start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        body = dict(
            repository_url=self.case.url,
            labels=[],
            state="open",
            issue_number=1,
            operation={
                "action": "close",
                "request_id": "server-error",
                "grant_ref": "grant",
            },
        )
        call = request.Request(
            f"http://127.0.0.1:{service.server_address[1]}/v1/github-issues/execute",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        with patch.object(
            self.case.gateway, "execute", side_effect=RuntimeError("dummy-secret")
        ):
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(call)
            self.assertEqual(caught.exception.code, 503)
            self.assertEqual(
                json.load(caught.exception), {"error_category": "issue_write_unknown"}
            )
