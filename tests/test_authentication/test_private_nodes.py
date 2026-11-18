"""Private node HTTP admission controls, not live GitHub or graph acceptance."""

from importlib.util import find_spec
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

if find_spec("langflow") is None:
    raise unittest.SkipTest("Optional Langflow runtime is not installed")

from starlette.requests import Request

from laomedo.github.node_runs.models import GitHubNodeReadResult
from laomedo.github.connections.models import (
    GitHubPrincipal,
    GitHubReadAuthorization,
    GitHubRepositoryIdentity,
)
from laomedo.integrations.langflow.authentication.boundary import (
    PrivateResponseBoundary,
)
from laomedo.integrations.langflow.authentication.errors import PrivateRequestRefused
from laomedo.integrations.langflow.authentication.private_nodes import private_node_read


class PrivateNodeReadTests(unittest.IsolatedAsyncioTestCase):
    """Body parsing and private bytes remain behind browser and resource guards."""

    def setUp(self):
        self.authorization = GitHubReadAuthorization(
            owner_id=uuid4(),
            connection_id=uuid4(),
            generation=1,
            repository=GitHubRepositoryIdentity(
                id=12, full_name="synthetic/private", private=True
            ),
            principal=GitHubPrincipal(id=34, login="synthetic"),
            deadline=60,
        )
        self.scope = SimpleNamespace(owner_id=self.authorization.owner_id)
        self.service = SimpleNamespace(
            read=AsyncMock(
                return_value=GitHubNodeReadResult(
                    authorization=self.authorization, payload={"prs": []}
                )
            )
        )
        self.app = SimpleNamespace(
            state=SimpleNamespace(private_github_nodes=self.service)
        )
        admission = patch(
            "laomedo.integrations.langflow.authentication.private_nodes.admit_private_request",
            new_callable=AsyncMock,
        )
        self.admit = admission.start()
        self.admit.return_value = self.scope
        self.addCleanup(admission.stop)

    def request(self, extra=None):
        payload = dict(
            connection_id=str(self.authorization.connection_id),
            kind="pr",
            repository_url="https://github.com/synthetic/private",
            labels=[],
            state="open",
            **(extra or {}),
        )
        self.receive = AsyncMock(
            return_value={"type": "http.request", "body": json.dumps(payload).encode()}
        )
        return Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/laomedo/private-github-nodes/discover",
                "headers": [(b"content-type", b"application/json")],
                "query_string": b"",
                "app": self.app,
            },
            self.receive,
        )

    async def test_admission_failure_does_not_parse_body_or_read_provider(self):
        request = self.request()
        self.admit.side_effect = PrivateRequestRefused()
        response = await private_node_read("discover", request, object())
        self.assertEqual(response.status_code, 409)
        self.receive.assert_not_awaited()
        self.service.read.assert_not_awaited()

    async def test_client_cannot_supply_owner_token_or_write_operation(self):
        for extra in (
            {"owner_id": str(uuid4())},
            {"token": "synthetic-secret"},
            {"operation": {"action": "close"}},
        ):
            response = await private_node_read(
                "discover", self.request(extra), object()
            )
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(b"synthetic-secret", response.body)
        self.service.read.assert_not_awaited()

    async def test_success_is_buffered_and_requires_resource_release_fence(self):
        request = self.request()
        response = await private_node_read("discover", request, object())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(
            request.state.github_response_binding.authorization, self.authorization
        )
        self.admit.assert_awaited_once_with(request, unittest.mock.ANY, mutating=True)
        self.service.read.assert_awaited_once_with(
            self.scope,
            action="discover",
            connection_id=self.authorization.connection_id,
            kind="pr",
            repository_url="https://github.com/synthetic/private",
            labels=[],
            state="open",
            number=None,
        )
        boundary = PrivateResponseBoundary(None, policy=None)
        self.assertTrue(boundary._private_path(request.url.path))
