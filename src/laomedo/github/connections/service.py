"""Owner/lease-bound connection lifecycle with durable generation and custody fences."""

import asyncio
from hmac import compare_digest
import time
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid4

from laomedo.github.connections.client import GitHubReadClient, GitHubRepositoryAccess
from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
    GitHubOAuthError,
    GitHubReauthorizationRequired,
    GitHubRepositoryAccessError,
    GitHubTokenUnsupported,
)
from laomedo.github.connections.models import (
    GitHubAppRecord,
    GitHubConnectionAttempt,
    GitHubConnectionCredential,
    GitHubConnectionRecord,
    GitHubConnectionScope,
    GitHubConnectionStatus,
    GitHubReadAuthorization,
)
from laomedo.github.connections.oauth import GitHubOAuthClient
from laomedo.github.connections.settings import (
    CONNECTION_ATTEMPT_SECONDS,
    CONNECTION_PENDING_LIMIT,
    GitHubAppSettings,
)


class GitHubConnectionService:
    """One native broker; every mutation commits under the shared admission lock."""

    def __init__(
        self,
        journal,
        vault,
        *,
        callback_uri,
        commit_lock,
        read_client=GitHubReadClient,
        oauth_client=GitHubOAuthClient,
        clock=time.time,
    ):
        """Inject admitted custody and transport owners, never ambient configuration."""
        self.journal, self.vault = journal, vault
        self.callback_uri = callback_uri
        self.commit_lock = commit_lock
        self.read_client, self.oauth_client = read_client, oauth_client
        self.clock = clock
        self.lock = asyncio.Lock()
        self.pending = {}

    def _same_lease(self, scope, attempt):
        """Compare the verified initiating owner and opaque browser-lease binding."""
        return scope.owner_id == attempt.owner_id and compare_digest(
            scope.lease_binding.get_secret_value().encode(),
            attempt.lease_binding.get_secret_value().encode(),
        )

    def _attempt(self, scope, request_id):
        """Refuse guessed, expired or other-session pending identities."""
        attempt = self.pending.get(request_id)
        if (
            attempt is None
            or not self._same_lease(scope, attempt)
            or attempt.expires_at <= self.clock()
        ):
            raise GitHubConnectionChanged()
        return attempt

    def _selected(self, scope, connection_id):
        """Resolve only an explicit owner-owned reconnect target."""
        if connection_id is None:
            return uuid4(), 0, None
        record = self.journal.get(scope.owner_id, connection_id)
        if record is None:
            raise GitHubConnectionChanged()
        return record.id, record.generation, record.principal.id

    def _app_settings(self, owner_id, app_id=None):
        """Load only the exact owned app version and its journaled vault reference."""
        app = self.journal.app(owner_id, app_id)
        if app is None:
            raise GitHubConnectionError()
        secret = self.vault.load(app.secret_reference)
        if secret is None:
            raise GitHubConnectionError()
        return app, GitHubAppSettings(
            client_id=app.client_id,
            slug=app.slug,
            client_secret=secret,
            callback_uri=self.callback_uri,
        )

    def _credential(self, record):
        """Restore matching custody only; a missing value cannot select another login."""
        value = self.vault.load(record.secret_reference)
        if value is None:
            raise GitHubReauthorizationRequired()
        try:
            credential = GitHubConnectionCredential.from_vault_value(value)
        except ValueError:
            raise GitHubReauthorizationRequired() from None
        if (
            credential.mode != record.mode
            or credential.access_expires_at != record.access_expires_at
            or credential.refresh_expires_at != record.refresh_expires_at
        ):
            raise GitHubReauthorizationRequired()
        return credential

    async def configure_app(
        self, scope: GitHubConnectionScope, *, client_id, slug, secret
    ):
        """Version deliberate app setup without rebinding existing ready connections."""
        settings = GitHubAppSettings(
            client_id=client_id,
            slug=slug,
            client_secret=secret,
            callback_uri=self.callback_uri,
        )
        async with self.lock, self.commit_lock:
            await scope.revalidate()
            app_id = uuid4()
            reference = self.journal.reserve_secret(scope.owner_id, "app", app_id)
            self.vault.store(reference.id, settings.client_secret)
            record = GitHubAppRecord(
                id=app_id,
                owner_id=scope.owner_id,
                client_id=settings.client_id,
                slug=settings.slug,
                secret_reference=reference.id,
            )
            self.journal.save_app(record)
            return record.model_dump(mode="json")

    async def _new_attempt(self, scope, mode, connection_id):
        """Create finite owner/lease-bound pending state after current admission."""
        await scope.revalidate()
        # Expired attempts are never live cleanup exclusions. Their reservations
        # remain in the durable journal until cleanup verifies absence.
        for key, attempt in tuple(self.pending.items()):
            if attempt.expires_at <= self.clock():
                self.pending.pop(key)
        if len(self.pending) >= CONNECTION_PENDING_LIMIT:
            raise GitHubConnectionError()
        selected_id, generation, principal_id = self._selected(scope, connection_id)
        return GitHubConnectionAttempt(
            id=uuid4(),
            owner_id=scope.owner_id,
            lease_binding=scope.lease_binding,
            connection_id=selected_id,
            expected_generation=generation,
            expected_principal_id=principal_id,
            mode=mode,
            expires_at=self.clock() + CONNECTION_ATTEMPT_SECONDS,
        )

    async def begin(
        self, scope: GitHubConnectionScope, connection_id: UUID | None = None
    ):
        """Start one browser-default attempt; previous ready state remains untouched."""
        async with self.lock:
            attempt = await self._new_attempt(scope, "browser", connection_id)
            app, settings = self._app_settings(scope.owner_id)
            oauth = await self.oauth_client(settings).begin()
            async with self.commit_lock:
                await scope.revalidate()
                attempt = attempt.model_copy(update={"app_id": app.id, "oauth": oauth})
                self.pending[attempt.id] = attempt
            return attempt.public()

    async def _stage(self, scope, attempt, credential):
        """Verify candidates before journaling and storing a provisional credential."""
        reader = self.read_client(credential)
        try:
            app = (
                self.journal.app(scope.owner_id, attempt.app_id)
                if attempt.app_id
                else None
            )
            inventory = await GitHubRepositoryAccess(reader).inventory(
                attempt.mode,
                app_slug=app.slug if app else None,
            )
            if (
                attempt.expected_principal_id is not None
                and inventory.principal.id != attempt.expected_principal_id
            ):
                raise GitHubRepositoryAccessError()
        finally:
            await reader.close()
        async with self.commit_lock:
            await scope.revalidate()
            if attempt.expires_at <= self.clock():
                raise GitHubConnectionChanged()
            reference = self.journal.reserve_secret(
                scope.owner_id, "connection", attempt.connection_id
            )
            self.vault.store(reference.id, credential.to_vault_value())
            staged = attempt.model_copy(
                update={
                    "oauth": None,
                    "inventory": inventory,
                    "secret_reference": reference.id,
                }
            )
            self.pending[staged.id] = staged
        return staged.public()

    async def begin_token(
        self, scope: GitHubConnectionScope, token, connection_id: UUID | None = None
    ):
        """Verify deliberate supported token entry; never infer refresh capability."""
        try:
            credential = GitHubConnectionCredential.from_token(token)
        except ValueError:
            raise GitHubTokenUnsupported() from None
        async with self.lock:
            attempt = await self._new_attempt(scope, "token", connection_id)
            return await self._stage(scope, attempt, credential)

    async def complete(self, scope: GitHubConnectionScope, callback_url):
        """Consume the exact initiating callback once, before any token exchange."""
        async with self.lock:
            await scope.revalidate()
            try:
                pairs = parse_qsl(
                    urlsplit(callback_url.get_secret_value()).query,
                    strict_parsing=True,
                    max_num_fields=10,
                )
                states = [value for key, value in pairs if key == "state"]
                if len(states) != 1 or not states[0] or len(states[0]) > 128:
                    raise GitHubOAuthError()
                attempt = next(
                    (
                        item
                        for item in self.pending.values()
                        if item.oauth is not None
                        and self._same_lease(scope, item)
                        and compare_digest(
                            item.oauth.state.get_secret_value().encode(),
                            states[0].encode(),
                        )
                    ),
                    None,
                )
                if attempt is None:
                    raise GitHubConnectionChanged()
                attempt = self._attempt(scope, attempt.id)
            except ValueError:
                raise GitHubOAuthError() from None
            self.pending.pop(attempt.id)
            _, settings = self._app_settings(scope.owner_id, attempt.app_id)
            credential = await self.oauth_client(settings).complete(
                attempt.oauth, callback_url
            )
            return await self._stage(scope, attempt, credential)

    async def confirm(
        self,
        scope: GitHubConnectionScope,
        request_id: UUID,
        repository_ids: tuple[int, ...],
    ):
        """Reverify explicit selected repositories, then CAS the new ready generation."""
        async with self.lock:
            await scope.revalidate()
            attempt = self._attempt(scope, request_id)
            if (
                attempt.inventory is None
                or attempt.secret_reference is None
                or not repository_ids
                or len(set(repository_ids)) != len(repository_ids)
                or any(type(value) is not int for value in repository_ids)
            ):
                raise GitHubConnectionChanged()
            available = {repo.id: repo for repo in attempt.inventory.repositories}
            if any(value not in available for value in repository_ids):
                raise GitHubRepositoryAccessError()
            value = self.vault.load(attempt.secret_reference)
            if value is None:
                raise GitHubReauthorizationRequired()
            credential = GitHubConnectionCredential.from_vault_value(value)
            reader = self.read_client(credential)
            try:
                access = GitHubRepositoryAccess(reader)
                repositories = tuple(
                    [
                        await access.verify(
                            attempt.inventory.principal, available[value]
                        )
                        for value in repository_ids
                    ]
                )
            finally:
                await reader.close()
            record = GitHubConnectionRecord(
                id=attempt.connection_id,
                owner_id=scope.owner_id,
                generation=attempt.expected_generation + 1,
                mode=attempt.mode,
                principal=attempt.inventory.principal,
                repositories=repositories,
                state="ready",
                app_id=attempt.app_id,
                secret_reference=attempt.secret_reference,
                access_expires_at=credential.access_expires_at,
                refresh_expires_at=credential.refresh_expires_at,
            )
            async with self.commit_lock:
                await scope.revalidate()
                self._attempt(scope, request_id)
                self.journal.commit_connection(
                    record, expected_generation=attempt.expected_generation
                )
                self.pending.pop(request_id)
            return record.model_dump(mode="json")

    async def cancel(self, scope: GitHubConnectionScope, request_id: UUID):
        """Abandon only this lease's pending request; never revoke ready state."""
        async with self.lock, self.commit_lock:
            await scope.revalidate()
            attempt = self._attempt(scope, request_id)
            self.pending.pop(request_id)
            if attempt.secret_reference is not None:
                self.journal.abandon_secret(scope.owner_id, attempt.secret_reference)
            removed = self._cleanup(scope.owner_id, resource_id=attempt.connection_id)
            return {
                "cancelled": True,
                "credential_cleanup_confirmed": removed,
                "provider_consent_revoked": False,
            }

    async def _refresh(self, scope, record):
        """Fence uncertainty before exchange and retain reauthorization on any failure."""
        credential = self._credential(record)
        if record.mode != "browser":
            raise GitHubReauthorizationRequired()
        _, settings = self._app_settings(scope.owner_id, record.app_id)
        async with self.commit_lock:
            await scope.revalidate()
            fenced = self.journal.begin_refresh(
                scope.owner_id, record.id, record.generation
            )
        # Anything after this durable fence may consume the old refresh token.
        replacement = await self.oauth_client(settings).refresh(credential)
        reader = self.read_client(replacement)
        try:
            access = GitHubRepositoryAccess(reader)
            principal = await access.principal()
            if principal.id != record.principal.id:
                raise GitHubRepositoryAccessError()
            repositories = tuple(
                [await access.verify(principal, repo) for repo in record.repositories]
            )
        finally:
            await reader.close()
        async with self.commit_lock:
            await scope.revalidate()
            reference = self.journal.reserve_secret(
                scope.owner_id, "connection", record.id
            )
            self.vault.store(reference.id, replacement.to_vault_value())
            updated = GitHubConnectionRecord(
                **{
                    **record.model_dump(),
                    "principal": principal,
                    "repositories": repositories,
                    "generation": fenced.generation + 1,
                    "secret_reference": reference.id,
                    "access_expires_at": replacement.access_expires_at,
                    "refresh_expires_at": replacement.refresh_expires_at,
                },
            )
            self.journal.commit_connection(
                updated, expected_generation=fenced.generation
            )
            return updated

    async def refresh(self, scope: GitHubConnectionScope, connection_id: UUID):
        """Perform a deliberate serialized renewal of a currently ready browser connection."""
        async with self.lock:
            await scope.revalidate()
            record = self.journal.get(scope.owner_id, connection_id)
            if record is None or record.state != "ready":
                raise GitHubReauthorizationRequired()
            updated = await self._refresh(scope, record)
            return updated.model_dump(mode="json")

    async def disconnect(
        self, scope: GitHubConnectionScope, connection_id: UUID, generation: int
    ):
        """Commit revocation first; leave failed removals fenced and retryable."""
        async with self.lock:
            async with self.commit_lock:
                await scope.revalidate()
                self.journal.disconnect(scope.owner_id, connection_id, generation)
                for key, attempt in tuple(self.pending.items()):
                    if (
                        attempt.owner_id == scope.owner_id
                        and attempt.connection_id == connection_id
                    ):
                        self.pending.pop(key)
            removed = self._cleanup(scope.owner_id, resource_id=connection_id)
            return {
                "disconnected": True,
                "credential_cleanup_confirmed": removed,
                "provider_consent_revoked": False,
            }

    def _cleanup(self, owner_id, resource_id=None):
        """Delete only inactive journaled references, excluding every live attempt."""
        live = {
            attempt.secret_reference
            for attempt in self.pending.values()
            if attempt.expires_at > self.clock()
            and attempt.secret_reference is not None
        }
        confirmed = True
        for reference in self.journal.cleanup_references(owner_id):
            if reference.id in live or (
                resource_id is not None and reference.resource_id != resource_id
            ):
                continue
            try:
                self.vault.remove(reference.id)
                self.journal.finish_cleanup(owner_id, reference.id)
            except Exception:
                confirmed = False
        return confirmed

    async def cleanup(self, scope: GitHubConnectionScope):
        """Retry exact retained local cleanup; never claim remote token revocation."""
        async with self.lock, self.commit_lock:
            await scope.revalidate()
            return {
                "credential_cleanup_confirmed": self._cleanup(scope.owner_id),
                "provider_consent_revoked": False,
            }

    async def authorize_read(
        self, scope: GitHubConnectionScope, connection_id: UUID, repository_id: int
    ):
        """Verify current consent/account/repository online before every private user read."""
        async with self.lock:
            await scope.revalidate()
            record = self.journal.get(scope.owner_id, connection_id)
            if record is None or record.state != "ready":
                raise GitHubReauthorizationRequired()
            if (
                record.access_expires_at is not None
                and record.access_expires_at <= self.clock()
            ):
                record = await self._refresh(scope, record)
            repository = next(
                (repo for repo in record.repositories if repo.id == repository_id), None
            )
            if repository is None:
                raise GitHubRepositoryAccessError()
            credential = self._credential(record)
            reader = self.read_client(credential)
            try:
                repository = await GitHubRepositoryAccess(reader).verify(
                    record.principal, repository
                )
                authorization = GitHubReadAuthorization(
                    owner_id=scope.owner_id,
                    connection_id=record.id,
                    generation=record.generation,
                    repository=repository,
                    principal=record.principal,
                    deadline=reader.deadline,
                )
            finally:
                await reader.close()
            async with self.commit_lock:
                await scope.revalidate()
                if not self.current(authorization):
                    raise GitHubConnectionChanged()
            return authorization

    def current(self, authorization: GitHubReadAuthorization):
        """Recheck exact owner/generation/repository consent under the response lock."""
        record = self.journal.get(authorization.owner_id, authorization.connection_id)
        return (
            record is not None
            and record.state == "ready"
            and record.generation == authorization.generation
            and any(
                repo.id == authorization.repository.id for repo in record.repositories
            )
        )

    def reader(self, authorization: GitHubReadAuthorization):
        """Open a host-only reader without resetting the admitted user-read deadline."""
        if not self.current(authorization):
            raise GitHubConnectionChanged()
        record = self.journal.get(authorization.owner_id, authorization.connection_id)
        reader = self.read_client(self._credential(record))
        reader.deadline = min(reader.deadline, authorization.deadline)
        return reader

    async def status(self, scope: GitHubConnectionScope):
        """Expose only this profile/lease's metadata, not a cached permission claim."""
        async with self.lock, self.commit_lock:
            await scope.revalidate()
            app = self.journal.app(scope.owner_id)
            live = {
                attempt.secret_reference
                for attempt in self.pending.values()
                if attempt.expires_at > self.clock()
            }
            cleanup = tuple(
                reference
                for reference in self.journal.cleanup_references(scope.owner_id)
                if reference.id not in live
            )
            connections = []
            for record in self.journal.list(scope.owner_id):
                availability = record.state
                if record.state == "ready":
                    try:
                        credential = self._credential(record)
                        if (
                            credential.access_expires_at is not None
                            and credential.access_expires_at <= self.clock()
                        ):
                            availability = "expired"
                    except Exception:
                        availability = "unavailable"
                connections.append(
                    GitHubConnectionStatus(
                        connection=record,
                        availability=availability,
                        credential_cleanup_pending=any(
                            ref.resource_id == record.id for ref in cleanup
                        ),
                    ).model_dump(mode="json")
                )
            return {
                "app": app.model_dump(mode="json") if app else None,
                "callback_uri": self.callback_uri,
                "connections": connections,
                "pending": [
                    attempt.public()
                    for attempt in self.pending.values()
                    if self._same_lease(scope, attempt)
                    and attempt.expires_at > self.clock()
                ],
                "credential_cleanup_pending": bool(cleanup),
            }
