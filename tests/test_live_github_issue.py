import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit
from urllib.parse import parse_qs
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.mediation.store import MediationStore
from laomedo.host.mediation.errors import MediationError


def raw_issue(number, labels, state="open"):
    return {
        "number": number,
        "repository_url": "https://api.github.com/repos/owner/repo",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "node_id": "I_" + str(number),
        "title": "Task " + str(number),
        "body": "Current issue body",
        "state": state,
        "updated_at": "2026-10-13T00:00:00Z",
        "labels": [{"name": label} for label in labels],
    }


class FakeGitHub:
    def __init__(self):
        self.issues = {
            1: raw_issue(1, ["research", "backend"]),
            2: raw_issue(2, ["research"]),
            3: raw_issue(3, ["backend"]),
            4: {**raw_issue(4, ["research", "backend"]), "pull_request": {}},
        }
        self.patch_count = 0
        self.timeout_after_write = False
        self.full_pages = False
        self.reject_patch = False

    def open(self, call, timeout=15):
        path = urlsplit(call.full_url).path
        query = parse_qs(urlsplit(call.full_url).query)
        method = call.get_method()
        if path.endswith("/labels"):
            value = [{"name": "backend"}, {"name": "research"}]
        elif path.endswith("/issues"):
            if self.full_pages:
                page = int(query["page"][0])
                value = [
                    raw_issue(n, ["backend"])
                    for n in range(page * 100, page * 100 + 100)
                ]
            else:
                value = [
                    copy.deepcopy(v)
                    for v in self.issues.values()
                    if query.get("state", ["open"])[0] in {"all", v["state"]}
                ]
        else:
            number = int(path.rsplit("/", 1)[1])
            value = copy.deepcopy(self.issues[number])
            if method == "PATCH":
                self.patch_count += 1
                if self.reject_patch:
                    from urllib.error import HTTPError

                    raise HTTPError(
                        call.full_url, 422, "dummy-provider-secret", {}, None
                    )
                changes = json.loads(call.data)
                for key, item in changes.items():
                    value[key] = (
                        [{"name": x} for x in item] if key == "labels" else item
                    )
                value["updated_at"] = "2026-10-13T00:01:00Z"
                self.issues[number] = copy.deepcopy(value)
                if self.timeout_after_write:
                    raise TimeoutError("dummy-provider-secret https://private.invalid")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self, limit):
                return json.dumps(value).encode()[:limit]

        return Response()


class LiveGitHubIssueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = [100.0]
        self.store = MediationStore(
            Path(self.temp.name) / "mediation.sqlite", now=lambda: self.clock[0]
        )
        self.fake = FakeGitHub()
        self.transport = GitHubRestTransport(
            "owner/repo", lambda: "DUMMY-PROVIDER-SECRET", opener=self.fake
        )
        self.grant_id, token = self.store.issue(
            run_id="run",
            invocation_id="invocation",
            repository="owner/repo",
            operations={"issue_update"},
            target_issues={1},
            ttl_seconds=60,
        )
        self.binding = {"token": token, "run_id": "run", "repository": "owner/repo"}
        self.gateway = GitHubIssueGateway(
            {"owner/repo": self.transport},
            self.store,
            lambda ref: self.binding if ref == "grant" else None,
        )
        self.url = "https://github.com/owner/repo"

    def execute(self, action="close", changes=None, request_id="effect"):
        op = {"action": action, "request_id": request_id, "grant_ref": "grant"}
        if changes is not None:
            op["changes"] = changes
        return self.gateway.execute(self.url, [], "open", 1, op)

    def test_all_labels_filter_and_pr_exclusion(self):
        result = self.gateway.discover(self.url, ["research", "backend"])
        self.assertEqual([v["number"] for v in result["issues"]], [1])
        self.assertEqual(len(self.gateway.discover(self.url, [])["issues"]), 3)

    def test_fresh_read_and_changed_filter_refusal(self):
        self.fake.issues[1]["body"] = "Changed on GitHub"
        self.assertEqual(
            self.gateway.execute(self.url, [], "open", 1)["issue"]["body"],
            "Changed on GitHub",
        )
        with self.assertRaisesRegex(ValueError, "no_longer_matches"):
            self.gateway.execute(self.url, ["backend"], "open", 2)

    def test_close_and_restart_replay_send_one_patch(self):
        result = self.execute()
        self.assertEqual(result["operation"]["status"], "succeeded")
        self.assertEqual(result["issue"]["state"], "closed")
        restarted = GitHubIssueGateway(
            {"owner/repo": self.transport}, self.store, lambda _: self.binding
        )
        self.assertEqual(
            restarted.execute(
                self.url,
                [],
                "open",
                1,
                {"action": "close", "request_id": "effect", "grant_ref": "grant"},
            ),
            result,
        )
        self.assertEqual(self.fake.patch_count, 1)

    def test_modify_title_body_and_labels(self):
        result = self.execute(
            "modify", {"title": "Changed", "body": "", "labels": ["research"]}
        )
        self.assertEqual(result["operation"]["status"], "succeeded")
        self.assertEqual(result["issue"]["title"], "Changed")
        self.assertEqual(result["issue"]["body"], "")
        self.assertEqual(result["issue"]["labels"], ["research"])

    def test_timeout_after_effect_stays_unknown_and_never_repeats(self):
        self.fake.timeout_after_write = True
        first = self.execute()
        self.assertEqual(first["operation"]["status"], "unknown")
        self.assertEqual(self.execute(), first)
        self.assertEqual(self.fake.patch_count, 1)
        self.assertNotIn("dummy-provider-secret", json.dumps(first))
        second = self.gateway.execute(
            self.url,
            [],
            "all",
            1,
            {"action": "close", "request_id": "new-effect", "grant_ref": "grant"},
        )
        self.assertEqual(second["operation"]["status"], "failed")
        self.assertEqual(self.fake.patch_count, 1)

    def test_known_rejection_and_payload_identity(self):
        self.fake.reject_patch = True
        self.assertEqual(self.execute()["operation"]["status"], "failed")
        with self.assertRaisesRegex(ValueError, "operation_conflict"):
            self.execute("modify", {"title": "Other"})
        self.assertEqual(self.fake.patch_count, 1)

    def test_expiry_revocation_and_foreign_target(self):
        self.clock[0] = 200
        self.assertEqual(
            self.execute()["operation"]["error_category"], "grant_unavailable"
        )
        self.clock[0] = 100
        self.store.revoke_run("run")
        self.assertEqual(
            self.execute(request_id="next")["operation"]["status"], "failed"
        )
        self.assertEqual(self.fake.patch_count, 0)

    def test_grant_requires_explicit_issue_targets(self):
        with self.assertRaises(MediationError):
            self.store.issue(
                run_id="other",
                invocation_id="other",
                repository="owner/repo",
                operations={"issue_update"},
                ttl_seconds=60,
            )
        result = self.gateway.execute(
            self.url,
            [],
            "open",
            2,
            {"action": "close", "request_id": "wrong", "grant_ref": "grant"},
        )
        self.assertEqual(result["operation"]["error_category"], "issue_target_denied")
        self.assertEqual(self.fake.patch_count, 0)

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
                self.gateway.execute(self.url, [], "open", 1, op)
        self.assertEqual(self.fake.patch_count, 0)

    def test_incomplete_pagination_is_not_empty_success(self):
        self.fake.full_pages = True
        with self.assertRaisesRegex(ValueError, "discovery_incomplete"):
            self.gateway.discover(self.url, [])

    def test_concurrent_duplicate_returns_unknown_then_confirmed_without_redispatch(
        self,
    ):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        entered, release = threading.Event(), threading.Event()
        original = self.fake.open

        def blocked(call, timeout=15):
            if call.get_method() == "PATCH":
                entered.set()
                if not release.wait(5):
                    raise TimeoutError()
            return original(call, timeout)

        self.fake.open = blocked
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
        self.assertEqual(self.fake.patch_count, 1)

    def test_loopback_service_auth_and_error_redaction(self):
        import threading
        from urllib import request
        from urllib import error
        from laomedo.github.interface.issues.server import IssueServer as server

        token = "dummy-control-" + "x" * 40
        service = server(self.gateway, token, port=0)
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        url = f"http://127.0.0.1:{service.server_address[1]}/v1/github-issues/discover"
        payload = json.dumps(
            {"repository_url": self.url, "labels": [], "state": "open"}
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
        original = self.fake.open
        reads = [0]

        def revoke_on_read(call, timeout=15):
            if call.get_method() == "GET" and call.full_url.endswith("/issues/1"):
                reads[0] += 1
                if reads[0] == 2:
                    self.store.revoke_run("run")
            return original(call, timeout)

        self.fake.open = revoke_on_read
        result = self.execute("modify", {"title": "Should not change"})
        self.assertEqual(result["operation"]["status"], "failed")
        self.assertEqual(self.fake.patch_count, 0)
        self.assertEqual(self.fake.issues[1]["title"], "Task 1")

    def test_rebinding_a_reference_cannot_reuse_another_runs_result(self):
        self.execute()
        _, replacement = self.store.issue(
            run_id="other-run",
            invocation_id="other-invoke",
            repository="owner/repo",
            operations={"issue_update"},
            target_issues={1},
            ttl_seconds=60,
        )
        self.binding = {
            "token": replacement,
            "run_id": "other-run",
            "repository": "owner/repo",
        }
        with self.assertRaisesRegex(ValueError, "issue_operation_conflict"):
            self.execute()
        self.assertEqual(self.fake.patch_count, 1)

    def test_rejected_readback_after_patch_stays_unknown(self):
        from urllib.error import HTTPError

        original = self.fake.open

        def fail_readback(call, timeout=15):
            if call.get_method() == "GET" and self.fake.patch_count:
                raise HTTPError(call.full_url, 403, "dummy-provider-secret", {}, None)
            return original(call, timeout)

        self.fake.open = fail_readback
        result = self.execute()
        self.assertEqual(result["operation"]["status"], "unknown")
        self.assertEqual(self.execute(), result)
        self.assertEqual(self.fake.patch_count, 1)

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
            repository_url=self.url,
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
            patch("laomedo.github.interface.issues.client.request.build_opener") as opener,
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
        service = server(self.gateway, token, port=0)
        threading.Thread(target=service.serve_forever, daemon=True).start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        body = dict(
            repository_url=self.url,
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
            self.gateway, "execute", side_effect=RuntimeError("dummy-secret")
        ):
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(call)
            self.assertEqual(caught.exception.code, 503)
            self.assertEqual(
                json.load(caught.exception), {"error_category": "issue_write_unknown"}
            )
