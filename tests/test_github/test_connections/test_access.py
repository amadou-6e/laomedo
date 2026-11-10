"""GET-only permission controls against a synthetic API, not real acceptance."""

from importlib.util import find_spec
import unittest

if find_spec("httpx2") is None:
    raise unittest.SkipTest("Optional private-source HTTPX2 is not installed")

from httpx2 import MockTransport, Response
from pydantic import SecretStr

from laomedo.github.connections.client import GitHubReadClient, GitHubRepositoryAccess
from laomedo.github.connections.errors import GitHubRepositoryAccessError
from laomedo.github.connections.models import (
    GitHubConnectionCredential,
    GitHubPrincipal,
    GitHubRepositoryIdentity,
)


class GitHubRepositoryAccessTests(unittest.IsolatedAsyncioTestCase):
    """Exercise real HTTPX2 boundaries and account/repository identity checks."""

    async def asyncSetUp(self):
        """Use one explicit synthetic token and fixed-response provider."""
        self.requests = []
        self.user = {"id": 123, "login": "synthetic"}
        self.repository = {"id": 456, "full_name": "synthetic/private", "private": True}
        self.responses = {
            "/user": self.user,
            "/user/repos": [self.repository],
            "/repos/synthetic/private": self.repository,
            "/repos/synthetic/private/branches": [],
            "/user/installations": {
                "total_count": 1,
                "installations": [
                    {"id": 12, "app_slug": "synthetic-app", "suspended_at": None}
                ],
            },
            "/user/installations/12/repositories": {
                "total_count": 1,
                "repositories": [self.repository],
            },
        }
        self.clock = 0.0
        credential = GitHubConnectionCredential.from_token(
            SecretStr("github_pat_synthetic")
        )
        self.client = GitHubReadClient(
            credential,
            transport=MockTransport(self.respond),
            clock=lambda: self.clock,
        )
        self.addAsyncCleanup(self.client.close)
        self.access = GitHubRepositoryAccess(self.client)

    def respond(self, request):
        """Inspect only synthetic Authorization and destination, then emit test JSON."""
        self.requests.append(request)
        value = self.responses.get(request.url.path)
        if isinstance(value, Response):
            return value
        return Response(200, json=value)

    async def test_verified_inventory_does_not_mutate_or_infer_consent(self):
        """Both modes use only fixed authenticated GETs; no credential enters models."""
        for mode in ("browser", "token"):
            inventory = await self.access.inventory(mode, app_slug="synthetic-app")
            self.assertEqual(inventory.principal.id, 123)
            self.assertEqual(inventory.repositories[0].id, 456)
            self.assertNotIn("github_pat_", inventory.model_dump_json())
            self.assertNotIn("consent", inventory.model_dump())
        for request in self.requests:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.host, "api.github.com")
            self.assertEqual(
                request.headers["Authorization"], "Bearer github_pat_synthetic"
            )

    async def test_verified_empty_is_distinct_from_provider_failure(self):
        """An inaccessible installation is never reported as a successful empty list."""
        self.responses["/user/installations"] = {"total_count": 0, "installations": []}
        inventory = await self.access.inventory("browser", app_slug="synthetic-app")
        self.assertEqual(inventory.repositories, ())
        self.responses["/user/installations"] = Response(
            404, json={"message": "synthetic-private-detail"}
        )
        with self.assertRaises(GitHubRepositoryAccessError) as error:
            await self.access.inventory("browser", app_slug="synthetic-app")
        self.assertEqual(str(error.exception), "github_repository_access_unconfirmed")

    async def test_redirect_is_refused_without_forwarding_authorization(self):
        """Even an API redirect cannot forward the selected credential to another URL."""
        self.responses["/user"] = Response(
            302, headers={"Location": "https://evil.invalid/user"}
        )
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.access.principal()
        self.assertEqual(len(self.requests), 1)

    async def test_total_deadline_is_shared_across_all_requests(self):
        """Later cached-content checks cannot reset an exhausted user-read budget."""
        await self.access.principal()
        self.clock = 61.0
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.access.principal()
        self.assertEqual(len(self.requests), 1)

    async def test_wrong_principal_repository_transfer_and_missing_contents_refuse(
        self,
    ):
        """Metadata alone does not prove Contents read or the originally consented ID."""
        principal = GitHubPrincipal(**self.user)
        repository = GitHubRepositoryIdentity(**self.repository)
        result = await self.access.verify(principal, repository)
        self.assertEqual(result, repository)
        self.user["id"] = 999
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.access.verify(principal, repository)
        self.user["id"] = 123
        self.repository["id"] = 888
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.access.verify(principal, repository)
        self.repository["id"] = 456
        self.responses["/repos/synthetic/private/branches"] = Response(
            403, json={"message": "not allowed"}
        )
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.access.verify(principal, repository)

    async def test_wrong_app_and_incomplete_or_excess_inventory_refuse(self):
        """A candidate list must establish its installation origin and completeness."""
        for payload in (
            {"total_count": 2, "installations": []},
            {"total_count": 1001, "installations": []},
            {"total_count": 1, "installations": [{"id": 12, "app_slug": "other-app"}]},
            {
                "total_count": 1,
                "installations": [
                    {"id": 12, "app_slug": "synthetic-app", "suspended_at": "now"}
                ],
            },
        ):
            self.responses["/user/installations"] = payload
            with self.subTest(), self.assertRaises(GitHubRepositoryAccessError):
                await self.access.inventory("browser", app_slug="synthetic-app")

    async def test_arbitrary_urls_and_paths_never_reach_transport(self):
        """Only the fixed API surface can carry this private credential."""
        for path in (
            "https://evil.invalid/user",
            "//evil.invalid/user",
            "/user?access_token=bad",
            "/repos/synthetic/private/issues",
            "/repos/../private",
            "/user#fragment",
        ):
            with self.subTest(), self.assertRaises(GitHubRepositoryAccessError):
                await self.client.get(path)
        self.assertFalse(self.requests)
