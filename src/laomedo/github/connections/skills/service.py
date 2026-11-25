"""Fresh online admission for private discovery and retained Skill reads."""

import base64
from time import monotonic

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.repository import GitHubRepositoryReader
from laomedo.github.connections.skills.models import PrivateSkillResult
from laomedo.github.connections.skills.store import PrivateSkillStore
from laomedo.skills.registry.utils.diff import patch_for


class PrivateSkillAccess:
    """Compose bounded provider reads and private immutable storage without dispatch."""

    def __init__(self, connections, store: PrivateSkillStore, *, clock=monotonic):
        self.connections = connections
        self.store = store
        self.clock = clock

    async def _current(self, scope, authorization):
        """Call only under the broker commit lock, before local reads or publication."""
        await scope.revalidate()
        if authorization.deadline <= self.clock():
            raise GitHubRepositoryAccessError()
        if not self.connections.current(authorization):
            raise GitHubConnectionChanged()

    async def discover(self, scope, connection_id, repository_id):
        """Discover exact choices with fresh online authority and one shared budget."""
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        client = self.connections.reader(authorization)
        try:
            choices = await GitHubRepositoryReader(authorization, client).discover()
        finally:
            await client.close()
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            return PrivateSkillResult(
                authorization=authorization,
                payload={"skills": [choice.to_record() for choice in choices]},
            )

    async def revisions(self, scope, connection_id, repository_id, choice_id):
        """Retain only complete discovered bundles; never publish into a public store."""
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        client = self.connections.reader(authorization)
        try:
            reader = GitHubRepositoryReader(authorization, client)
            choice = next(
                (item for item in await reader.discover() if item.choice == choice_id),
                None,
            )
            if choice is None:
                raise GitHubRepositoryAccessError()
            revisions = await reader.revisions(choice)
        finally:
            await client.close()
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            origins = [
                self.store.retain(authorization, choice, revision)
                for revision in revisions
            ]
            await self._current(scope, authorization)
            return PrivateSkillResult(
                authorization=authorization,
                payload={
                    "revisions": [item.model_dump(mode="json") for item in origins]
                },
            )

    async def inspect(self, scope, connection_id, repository_id, skill_id, revision_id):
        """Reauthorize warm files, image and binary bytes before buffered inspection."""
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            payload = self.store.inspect(authorization, skill_id, revision_id)
            await self._current(scope, authorization)
            return PrivateSkillResult(authorization=authorization, payload=payload)

    async def history(self, scope, connection_id, repository_id, skill_id):
        """Current consent, not a retained hash, authorizes every history listing."""
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            origins = [
                item.model_dump(mode="json")
                for item in self.store.origins(authorization)
                if item.skill_id == skill_id
            ]
            await self._current(scope, authorization)
            return PrivateSkillResult(
                authorization=authorization, payload={"origins": origins}
            )

    def _files(self, snapshot):
        """Recover verified exact file inventories from the canonical inspector."""
        result = {}
        for item in snapshot["files"]:
            if item["text"] is not None:
                result[item["path"]] = item["text"].encode("utf-8")
            elif "binary_base64" in item:
                result[item["path"]] = base64.b64decode(
                    item["binary_base64"], validate=True
                )
            else:
                result[item["path"]] = base64.b64decode(
                    item["image_data_url"].split(",", 1)[1], validate=True
                )
        return result

    async def compare(
        self, scope, connection_id, repository_id, skill_id, before, after
    ):
        """One admission covers two exact revisions within the same private provenance."""
        authorization = await self.connections.authorize_read(
            scope, connection_id, repository_id
        )
        async with self.connections.commit_lock:
            await self._current(scope, authorization)
            base = self.store.inspect(authorization, skill_id, before)
            target = self.store.inspect(authorization, skill_id, after)
            payload = {"patch": patch_for(self._files(base), self._files(target))}
            await self._current(scope, authorization)
            return PrivateSkillResult(authorization=authorization, payload=payload)
