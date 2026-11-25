"""Private Skill route admission and response bindings with synthetic services."""

from importlib.util import find_spec
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

if find_spec("langflow") is None:
    raise unittest.SkipTest("Optional Langflow runtime is not installed")

from starlette.requests import Request

from laomedo.github.connections.models import (
    GitHubPrincipal,
    GitHubReadAuthorization,
    GitHubRepositoryIdentity,
)
from laomedo.integrations.langflow.authentication.errors import PrivateRequestRefused
from laomedo.integrations.langflow.authentication.private_skills import (
    private_skill_action,
)
from laomedo.github.connections.skills.models import PrivateSkillResult


class PrivateSkillHttpTests(unittest.IsolatedAsyncioTestCase):
    """Private bytes require admission and the separate release-time resource proof."""

    def setUp(self):
        self.authorization = GitHubReadAuthorization(
            owner_id=uuid4(),
            connection_id=uuid4(),
            generation=1,
            repository=GitHubRepositoryIdentity(
                id=456, full_name="synthetic/private", private=True
            ),
            principal=GitHubPrincipal(id=123, login="synthetic"),
            deadline=60.0,
        )
        self.scope = SimpleNamespace(owner_id=self.authorization.owner_id)
        self.service = SimpleNamespace(
            discover=AsyncMock(
                return_value=PrivateSkillResult(
                    authorization=self.authorization, payload={"skills": []}
                )
            )
        )
        self.app = SimpleNamespace(
            state=SimpleNamespace(private_skill_access=self.service)
        )
        admission = patch(
            "laomedo.integrations.langflow.authentication.private_skills._admit",
            new_callable=AsyncMock,
        )
        self.admit = admission.start()
        self.addCleanup(admission.stop)
        self.admit.return_value = self.scope

    def request(self, extra=None):
        body = {
            "connection_id": str(self.authorization.connection_id),
            "repository_id": 456,
            **(extra or {}),
        }
        self.receive = AsyncMock(
            return_value={"type": "http.request", "body": json.dumps(body).encode()}
        )
        return Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/laomedo/private-skills/discover",
                "headers": [(b"content-type", b"application/json")],
                "query_string": b"",
                "app": self.app,
            },
            self.receive,
        )

    async def test_admission_failure_precedes_body_or_private_service(self):
        request = self.request()
        self.admit.side_effect = PrivateRequestRefused()
        response = await private_skill_action("discover", request, object())
        self.assertEqual(response.status_code, 409)
        self.receive.assert_not_awaited()
        self.service.discover.assert_not_awaited()

    async def test_browser_cannot_choose_owner_or_supply_credential(self):
        for extra in (
            {"owner_id": str(uuid4())},
            {"token": "synthetic-secret"},
            {"repository_id": True},
        ):
            response = await private_skill_action(
                "discover", self.request(extra), object()
            )
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(b"synthetic-secret", response.body)
        self.service.discover.assert_not_awaited()

    async def test_buffered_success_installs_exact_authorization_for_release(self):
        request = self.request()
        response = await private_skill_action("discover", request, object())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(
            request.state.github_response_binding.authorization, self.authorization
        )
        self.admit.assert_awaited_once_with(request, unittest.mock.ANY, mutating=True)
        self.service.discover.assert_awaited_once_with(
            self.scope, self.authorization.connection_id, 456
        )
