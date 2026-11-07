"""Issue loopback/client controls with fresh concern-owned gateway state."""

import json
from pathlib import Path
import tempfile
import unittest
from test_github.test_issues.utils import create_case


class IssueHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)

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
