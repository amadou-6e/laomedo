"""Bounded fixed-origin repository reads using only the selected credential."""

import asyncio
import json
import re
from ssl import PROTOCOL_TLS_CLIENT
from time import monotonic

from httpx2 import AsyncClient, AsyncHTTPTransport
from truststore import SSLContext

from laomedo.github.connections.errors import GitHubRepositoryAccessError
from laomedo.github.connections.models import (
    GitHubPrincipal,
    GitHubRepositoryIdentity,
    GitHubRepositoryInventory,
    GitHubReadPage,
)
from laomedo.github.connections.settings import (
    GITHUB_API_ORIGIN,
    GITHUB_API_VERSION,
    GITHUB_READ_DEADLINE_SECONDS,
    GITHUB_READ_RESPONSE_LIMIT,
    GITHUB_READ_TOTAL_BYTES,
    GITHUB_REPOSITORY_LIMIT,
)


class GitHubReadClient:
    """One private user operation's GET-only client and total network deadline."""

    def __init__(self, credential, *, transport=None, clock=monotonic):
        """Bind explicit secret custody; never inspect host login or environment."""
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + GITHUB_READ_DEADLINE_SECONDS
        self.read_bytes = 0
        self.client = AsyncClient(
            headers={
                "Authorization": "Bearer " + credential.access_token.get_secret_value(),
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "Laomedo-private-skill-reader",
            },
            trust_env=False,
            follow_redirects=False,
            timeout=GITHUB_READ_DEADLINE_SECONDS,
            transport=(
                transport
                if transport is not None
                else AsyncHTTPTransport(
                    verify=SSLContext(PROTOCOL_TLS_CLIENT),
                    trust_env=False,
                    retries=0,
                )
            ),
        )

    def _path(self, path: str):
        """Admit exact API namespaces; credential-bearing target URLs are never input."""
        if (
            not isinstance(path, str)
            or not re.fullmatch(
                r"/(?:user(?:/repos|/installations(?:/[1-9][0-9]*/repositories)?)?"
                r"|repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
                r"(?:/branches|/git/(?:matching-refs/(?:heads|tags)/|"
                r"(?:commits|trees|blobs|tags)/[0-9a-f]{40}))?)",
                path,
            )
            or ".." in path
        ):
            raise GitHubRepositoryAccessError()

    async def get_page(self, path: str, *, params=None):
        """Return bounded JSON from one fixed GET without following provider links."""
        self._path(path)
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise GitHubRepositoryAccessError()
        try:
            async with asyncio.timeout(remaining):
                async with self.client.stream(
                    "GET", GITHUB_API_ORIGIN + path, params=params
                ) as response:
                    if response.status_code != 200:
                        raise GitHubRepositoryAccessError()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        self.read_bytes += len(chunk)
                        if (
                            len(body) + len(chunk) > GITHUB_READ_RESPONSE_LIMIT
                            or self.read_bytes > GITHUB_READ_TOTAL_BYTES
                        ):
                            raise GitHubRepositoryAccessError()
                        body.extend(chunk)
                    value = json.loads(body)
                    if not isinstance(value, (dict, list)):
                        raise GitHubRepositoryAccessError()
                    return GitHubReadPage(
                        payload=value, next_page="next" in response.links
                    )
        except Exception:
            raise GitHubRepositoryAccessError() from None

    async def get(self, path: str, *, params=None):
        """Return bounded JSON; completeness-sensitive callers also inspect get_page."""
        return (await self.get_page(path, params=params)).payload

    async def close(self):
        """Close only this private operation's transport and sockets."""
        await self.client.aclose()


class GitHubRepositoryAccess:
    """Verify actual account/repository access, distinct from local read consent."""

    def __init__(self, client: GitHubReadClient):
        """Share the operation's selected credential and finite total deadline."""
        self.client = client

    async def principal(self):
        """Resolve only the account actually authenticated by this credential."""
        try:
            data = await self.client.get("/user")
            return GitHubPrincipal(id=data["id"], login=data["login"])
        except Exception:
            raise GitHubRepositoryAccessError() from None

    async def _pages(self, path, key=None):
        """Establish completeness within the bound; never hide excess candidates."""
        items = []
        total = None
        for page in range(1, GITHUB_REPOSITORY_LIMIT // 100 + 2):
            response = await self.client.get_page(
                path, params={"per_page": 100, "page": page}
            )
            value = response.payload
            if key:
                count = value.get("total_count") if isinstance(value, dict) else None
                if (
                    type(count) is not int
                    or not 0 <= count <= GITHUB_REPOSITORY_LIMIT
                    or (total is not None and count != total)
                ):
                    raise GitHubRepositoryAccessError()
                total = count
            batch = value.get(key) if key and isinstance(value, dict) else value
            if not isinstance(batch, list) or len(batch) > 100:
                raise GitHubRepositoryAccessError()
            items.extend(batch)
            if len(items) > GITHUB_REPOSITORY_LIMIT:
                raise GitHubRepositoryAccessError()
            if len(batch) < 100 and not response.next_page:
                if total is not None and len(items) != total:
                    raise GitHubRepositoryAccessError()
                return items
        raise GitHubRepositoryAccessError()

    def _repository(self, data):
        """Project only numeric identity, current name and provider visibility."""
        try:
            return GitHubRepositoryIdentity(
                id=data["id"], full_name=data["full_name"], private=data["private"]
            )
        except Exception:
            raise GitHubRepositoryAccessError() from None

    async def inventory(self, mode, *, app_slug=None):
        """List verified candidates; an empty success remains distinct from failure."""
        principal = await self.principal()
        if mode == "browser":
            installations = await self._pages("/user/installations", "installations")
            candidates = []
            for installation in installations:
                if (
                    not isinstance(installation, dict)
                    or type(installation.get("id")) is not int
                    or installation["id"] <= 0
                    or installation.get("app_slug") != app_slug
                    or installation.get("suspended_at") is not None
                ):
                    raise GitHubRepositoryAccessError()
                candidates.extend(
                    await self._pages(
                        f"/user/installations/{installation['id']}/repositories",
                        "repositories",
                    )
                )
                if len(candidates) > GITHUB_REPOSITORY_LIMIT:
                    raise GitHubRepositoryAccessError()
        elif mode == "token":
            candidates = await self._pages("/user/repos")
        else:
            raise GitHubRepositoryAccessError()
        repositories = tuple(self._repository(data) for data in candidates)
        if len({repo.id for repo in repositories}) != len(repositories):
            raise GitHubRepositoryAccessError()
        return GitHubRepositoryInventory(
            principal=principal,
            repositories=repositories,
            elapsed_seconds=max(0, self.client.clock() - self.client.started),
        )

    async def verify(
        self, principal: GitHubPrincipal, repository: GitHubRepositoryIdentity
    ):
        """Recheck account, immutable repo identity and actual Contents-read access."""
        current = await self.principal()
        if current.id != principal.id:
            raise GitHubRepositoryAccessError()
        data = await self.client.get("/repos/" + repository.full_name)
        selected = self._repository(data)
        if (
            selected.id != repository.id
            or selected.full_name.lower() != repository.full_name.lower()
        ):
            raise GitHubRepositoryAccessError()
        # Branch listing requires Contents read; metadata alone proves less.
        branches = await self.client.get(
            "/repos/" + selected.full_name + "/branches", params={"per_page": 1}
        )
        if not isinstance(branches, list) or len(branches) > 1:
            raise GitHubRepositoryAccessError()
        return selected
