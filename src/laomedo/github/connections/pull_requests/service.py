"""Freshly authorized selected-account pull request reads."""

from datetime import datetime, timezone
from time import monotonic

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.pull_requests.models import PrivatePullRequestResult
from laomedo.github.contract import issue_digest
from laomedo.github.pull_requests.contract import pr_value


class PrivatePullRequestAccess:
    """Read PRs under current owner, account, and repository consent."""

    def __init__(self, connections, *, clock=monotonic):
        self.connections = connections
        self.clock = clock

    async def _current(self, scope, authorization):
        await scope.revalidate()
        if authorization.deadline <= self.clock():
            raise GitHubRepositoryAccessError()
        if not self.connections.current(authorization):
            raise GitHubConnectionChanged()

    async def discover(self, scope, connection_id, repository_id):
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        client = self.connections.reader(authorization)
        repository = authorization.repository.full_name
        items = []
        try:
            for page in range(1, 11):
                response = await client.get_page(
                    f"/repos/{repository}/pulls",
                    params={"state": "all", "per_page": 100, "page": page},
                )
                if not isinstance(response.payload, list):
                    raise GitHubRepositoryAccessError()
                for raw in response.payload:
                    pr = pr_value(
                        raw,
                        repository,
                        raw.get("number") if isinstance(raw, dict) else None,
                    )
                    items.append(
                        {
                            "choice": f"#{pr['number']} {pr['title']}",
                            "number": pr["number"],
                            "title": pr["title"],
                            "state": "merged" if pr["merged"] else pr["state"],
                            "labels": pr["labels"],
                        }
                    )
                if not response.next_page:
                    break
            else:
                raise GitHubRepositoryAccessError()
        finally:
            await client.close()
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            return PrivatePullRequestResult(
                authorization=authorization, payload={"prs": items}
            )

    async def read(self, scope, connection_id, repository_id, pr_number):
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        client = self.connections.reader(authorization)
        repository = authorization.repository.full_name
        try:
            raw = await client.get(f"/repos/{repository}/pulls/{pr_number}")
            pr = pr_value(raw, repository, pr_number)
        finally:
            await client.close()
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            return PrivatePullRequestResult(
                authorization=authorization,
                payload={
                    "schema_version": "laomedo.github-pr.v1",
                    "pr": pr,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "content_digest": issue_digest(pr),
                    "operation": {"status": "not_requested", "error_category": None},
                },
            )
