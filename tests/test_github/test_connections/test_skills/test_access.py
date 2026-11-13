"""Synthetic authority and immutable-provenance controls, not GitHub acceptance."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

from pydantic import SecretStr

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubRepositoryAccessError,
)
from laomedo.github.connections.models import (
    GitHubConnectionScope,
    GitHubReadAuthorization,
    GitHubPrincipal,
    GitHubRepositoryIdentity,
    GitHubSkillRevision,
)
from laomedo.github.connections.skills.service import PrivateSkillAccess
from laomedo.github.connections.skills.store import PrivateSkillStore
from laomedo.skills.sources.models import PendingSkillImport, SkillSourceChoice


class PrivateConnections:
    """Simulate fresh admission and independent generation changes without a token."""

    def __init__(self, authorization):
        self.authorization = authorization
        self.commit_lock = asyncio.Lock()
        self.reads = 0
        self.ready = True
        self.online = True
        self.now = 1.0

    def clock(self):
        return self.now

    def current(self, authorization):
        return self.ready and authorization == self.authorization

    async def authorize_read(self, scope, connection_id, repository_id):
        self.reads += 1
        await scope.revalidate()
        if (
            not self.online
            or scope.owner_id != self.authorization.owner_id
            or connection_id != self.authorization.connection_id
            or repository_id != self.authorization.repository.id
        ):
            raise GitHubRepositoryAccessError()
        return self.authorization


class PrivateSkillAccessTests(unittest.IsolatedAsyncioTestCase):
    """Protect retained bytes and every warm read from stale or cross-owner authority."""

    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
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
        self.checks = 0
        self.scope = GitHubConnectionScope(
            owner_id=self.authorization.owner_id,
            lease_binding=SecretStr("synthetic-lease"),
            check=self.check,
        )
        self.connections = PrivateConnections(self.authorization)
        self.store = PrivateSkillStore(self.root / "private")
        self.service = PrivateSkillAccess(
            self.connections, self.store, clock=self.connections.clock
        )
        self.choice = SkillSourceChoice.for_folder("synthetic", "skills/synthetic")
        self.first = self.retain(b"# First\n", "a")
        self.second = self.retain(b"# Second\n", "b")

    async def check(self):
        self.checks += 1

    def retain(self, content, commit):
        return self.store.retain(
            self.authorization,
            self.choice,
            GitHubSkillRevision(
                label="heads/" + commit,
                commit=commit * 40,
                candidate=PendingSkillImport(
                    files={"SKILL.md": content, "asset.bin": b"\x00\xff"},
                    origin="synthetic-private-origin",
                ),
            ),
        )

    def arguments(self):
        return (
            self.scope,
            self.authorization.connection_id,
            self.authorization.repository.id,
            self.first.skill_id,
        )

    async def test_every_warm_surface_reauthorizes_and_returns_after_unlock(self):
        snapshot = await self.service.inspect(*self.arguments(), self.first.revision_id)
        self.assertEqual(snapshot.payload["revision_id"], self.first.revision_id)
        history = await self.service.history(*self.arguments())
        self.assertEqual(len(history.payload["origins"]), 2)
        comparison = await self.service.compare(
            *self.arguments(), self.first.revision_id, self.second.revision_id
        )
        self.assertIn("First", comparison.payload["patch"])
        self.assertIn("Second", comparison.payload["patch"])
        self.assertEqual(self.connections.reads, 3)
        self.assertGreaterEqual(self.checks, 9)
        self.assertFalse(self.connections.commit_lock.locked())
        self.assertEqual(snapshot.authorization, self.authorization)

    async def test_offline_cannot_read_even_warm_history_binary_or_compare(self):
        self.connections.online = False
        calls = (
            self.service.inspect(*self.arguments(), self.first.revision_id),
            self.service.history(*self.arguments()),
            self.service.compare(
                *self.arguments(), self.first.revision_id, self.second.revision_id
            ),
        )
        for call in calls:
            with self.assertRaises(GitHubRepositoryAccessError):
                await call

    async def test_generation_change_or_deadline_refuses_retained_bytes(self):
        self.connections.ready = False
        with self.assertRaises(GitHubConnectionChanged):
            await self.service.inspect(*self.arguments(), self.first.revision_id)
        self.connections.ready = True
        self.connections.now = 61.0
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.history(*self.arguments())
        self.assertFalse(self.connections.commit_lock.locked())

    async def test_same_hash_cannot_cross_owner_connection_or_repository(self):
        for change in (
            {"owner_id": uuid4()},
            {"connection_id": uuid4()},
            {
                "repository": self.authorization.repository.model_copy(
                    update={"id": 999}
                )
            },
        ):
            other = self.authorization.model_copy(update=change)
            self.assertEqual(self.store.origins(other), ())
            with self.assertRaises(GitHubRepositoryAccessError):
                self.store.inspect(other, self.first.skill_id, self.first.revision_id)

    async def test_unjournaled_immutable_bytes_confer_no_read_authority(self):
        namespace = self.store._namespace(self.authorization)
        for path in (namespace / "origins").glob("*.json"):
            path.unlink()
        self.assertTrue((namespace / "registry" / "skills").exists())
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.inspect(*self.arguments(), self.first.revision_id)

    async def test_origin_tampering_fails_closed_and_public_root_is_untouched(self):
        namespace = self.store._namespace(self.authorization)
        path = next((namespace / "origins").glob("*.json"))
        path.write_text(
            path.read_text().replace(str(self.authorization.owner_id), str(uuid4()))
        )
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.service.history(*self.arguments())
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["private"])
