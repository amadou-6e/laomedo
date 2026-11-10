"""Private HTTP controls never echo credential input or admit owner selection."""

from importlib.util import find_spec
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

if find_spec("langflow") is None:
    raise unittest.SkipTest("Optional Langflow runtime is not installed")

from starlette.requests import Request

from laomedo.integrations.langflow.authentication.connections import (
    connection_action,
    connection_callback,
    connection_index,
)
from laomedo.integrations.langflow.authentication.errors import PrivateRequestRefused
from laomedo.github.connections.settings import CONNECTION_BODY_BYTES


class PrivateConnectionHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.owner = uuid4()
        self.scope = SimpleNamespace(owner_id=self.owner)
        self.service = SimpleNamespace(
            status=AsyncMock(return_value={"revision": 9, "connections": []}),
            begin_token=AsyncMock(return_value={"phase": "consent"}),
            complete=AsyncMock(),
        )
        self.policy = SimpleNamespace(
            authorize=AsyncMock(return_value=object()),
            mutation=Mock(),
            callback=AsyncMock(),
        )
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                private_access_policy=self.policy,
                private_github_connections=self.service,
            )
        )
        admission = patch(
            "laomedo.integrations.langflow.authentication.connections.PrivateGitHubAdmission"
        )
        self.admission = admission.start()
        self.admission.return_value.scope.return_value = self.scope
        self.addCleanup(admission.stop)

    def request(
        self, body=b"{}", *, method="POST", query=b"", content_type=b"application/json"
    ):
        self.receive = AsyncMock(return_value={"type": "http.request", "body": body})
        return Request(
            {
                "type": "http",
                "method": method,
                "scheme": "http",
                "path": (
                    "/api/v1/laomedo/github-connections/callback"
                    if method == "GET"
                    else "/api/v1/laomedo/github-connections/token"
                ),
                "query_string": query,
                "headers": [
                    (b"host", b"127.0.0.1:17867"),
                    (b"content-type", content_type),
                ],
                "server": ("127.0.0.1", 17867),
                "app": self.app,
            },
            self.receive,
        )

    async def test_csrf_failure_precedes_secret_body_ingestion(self):
        request = self.request(b'{"token":"sensitive-example"}')
        self.policy.mutation.side_effect = PrivateRequestRefused()
        response = await connection_action("token", request, object())
        self.assertEqual(response.status_code, 409)
        self.receive.assert_not_awaited()
        self.service.begin_token.assert_not_awaited()
        self.assertNotIn(b"sensitive-example", response.body)

    async def test_invalid_bodies_never_echo_credentials_or_call_service(self):
        payloads = (
            b'{"token":"sensitive-example","owner_id":"forged"}',
            b'{"token":"sensitive-example","token":"second"}',
            b'{"token":',
            b"[]",
            b"x" * (CONNECTION_BODY_BYTES + 1),
        )
        for payload in payloads:
            with self.subTest(length=len(payload)):
                response = await connection_action(
                    "token", self.request(payload), object()
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    json.loads(response.body),
                    {"code": "github_connection_input_invalid"},
                )
        self.service.begin_token.assert_not_awaited()

    async def test_explicit_token_is_secret_and_owner_comes_from_admission(self):
        request = self.request(b'{"token":"sensitive-example"}')
        response = await connection_action("token", request, object())
        self.assertEqual(response.status_code, 200)
        args = self.service.begin_token.await_args.args
        self.assertIs(args[0], self.scope)
        self.assertEqual(args[1].get_secret_value(), "sensitive-example")
        self.assertNotIn(b"sensitive-example", response.body)
        binding = request.state.github_response_binding
        self.assertEqual((binding.owner_id, binding.revision), (self.owner, 9))

    async def test_service_exception_diagnostics_are_not_serialized(self):
        self.service.status.side_effect = RuntimeError("sensitive-example")
        response = await connection_index(self.request(method="GET"), object())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            json.loads(response.body), {"code": "github_connection_unavailable"}
        )

    async def test_callback_failure_cannot_forward_code_or_external_return(self):
        self.policy.callback.side_effect = PrivateRequestRefused()
        request = self.request(
            method="GET",
            query=b"code=sensitive-example&state=secret&return=https://example.org",
        )
        response = await connection_callback(request)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/settings/github?outcome=authorization-unconfirmed",
        )
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.service.complete.assert_not_awaited()

    async def test_callback_success_forwards_only_trusted_pending_reference(self):
        reference = str(uuid4())
        self.service.complete.return_value = {"request_id": reference}
        response = await connection_callback(
            self.request(method="GET", query=b"code=sensitive-example&state=secret")
        )
        self.assertEqual(
            response.headers["location"],
            "/settings/github?outcome=consent&request=" + reference,
        )
        self.assertNotIn("sensitive-example", response.headers["location"])
