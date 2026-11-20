"""Shared owner/generation admission and provider lifecycle orchestration."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from uuid import UUID


from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import (
    _atomic_private,
    _outside_git,
    _restrict_windows_directory,
    _locked,
)
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import (
    GraphProviderPreferences,
    ConnectionRecord,
    ConnectionIndex,
    ConnectionSummary,
    LoginProgress,
    DisconnectInfo,
    DisconnectProgress,
)


class ProviderConnections:
    """Own one local runtime's saved credentials; never select a default account.

    This service is installed only in the single-worker local-profile runtime.
    The instance lock fences late callbacks against cancellation and logout. A
    restart discards all pending authorizations rather than replaying them.
    """

    def __init__(self, root: Path):
        """Admit a private root outside Git; do not inspect any ambient login."""
        self.root = _outside_git(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _restrict_windows_directory(self.root)
        self._lock = threading.RLock()
        self._closing = False
        from laomedo.agents.agents.codex.connection import CodexConnection
        from laomedo.agents.agents.claude.connection import ClaudeConnection
        from laomedo.agents.agents.opencode.connection import GoConnection

        self.go = GoConnection(self)
        self.claude = ClaudeConnection(self)
        self.codex = CodexConnection(self)
        self.adapters = (self.go, self.claude, self.codex)
        self.controllers = None
        self.revoked_leases: set[str] = set()
        owner_path = self.root / "owner.lock"
        try:
            descriptor = os.open(
                owner_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(b"0")
        self._ownership = _locked(owner_path)
        self._ownership.__enter__()
        try:
            self._reconcile_stores()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Fence pending callbacks and release this runtime's exclusive store lease."""
        with self._lock:
            if self._closing:
                return
            self._closing = True
            for adapter in self.adapters:
                adapter.fence_all()
            workers = [
                worker for adapter in self.adapters for worker in adapter.workers()
            ]
        deadline = time.monotonic() + max(
            adapter.cleanup_seconds for adapter in self.adapters
        )
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in workers):
            # Do not release custody while a native worker could still finish.
            # The daemon finisher retains the lease without blocking app shutdown.
            threading.Thread(
                target=self._finish_close, args=(workers,), daemon=True
            ).start()
        else:
            self._finish_close(workers)

    def graph_preferences(
        self, profile_id: UUID, flow_id: UUID
    ) -> GraphProviderPreferences:
        """Read only this profile's graph selection; corrupt state never becomes empty."""
        with self._lock:
            path = self._profile(profile_id) / (
                "graph-" + str(UUID(str(flow_id))) + ".json"
            )
            if not path.exists():
                return GraphProviderPreferences()
            try:
                return GraphProviderPreferences.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                raise ProviderConnectionError(
                    "provider_connections_unavailable"
                ) from None

    def save_graph_preferences(
        self, profile_id: UUID, flow_id: UUID, preferences: GraphProviderPreferences
    ) -> GraphProviderPreferences:
        """Save one graph's explicit account choice without changing any node or login."""
        with self._lock:
            for provider, connection_id in preferences.model_dump().items():
                if connection_id is None:
                    continue
                record = self._record(profile_id, connection_id)
                if record.provider != provider:
                    raise ProviderConnectionError("provider_connection_unavailable")
                if record.lifecycle != "connected":
                    raise ProviderConnectionError("provider_connection_disconnecting")
                if record.provider == "opencode":
                    self.go.profile(profile_id, record)
            path = self._profile(profile_id) / (
                "graph-" + str(UUID(str(flow_id))) + ".json"
            )
            _atomic_private(path, preferences.model_dump(mode="json"))
            return preferences.model_copy()

    def admitted(
        self, profile_id: UUID, connection_id: UUID, generation: int | None = None
    ) -> ConnectionRecord:
        """Check ownership and durable fence; callers hold the lifecycle lock."""
        record = self._record(profile_id, connection_id)
        if record.lifecycle != "connected":
            raise ProviderConnectionError("provider_connection_disconnecting")
        if generation is not None and record.generation != generation:
            raise ProviderConnectionError("provider_connection_changed")
        return record

    def disconnect_info(self, profile_id: UUID, connection_id: UUID) -> DisconnectInfo:
        """Inspect affected owned work without starting or stopping a controller."""
        with self._lock:
            record = self._record(profile_id, connection_id)
            if self.controllers is None:
                raise ProviderConnectionError("provider_runner_unavailable")
            count, revision = self.controllers.inventory(profile_id, connection_id)
            return DisconnectInfo(
                connection_id=connection_id,
                generation=record.generation,
                active_runs=count,
                revision=revision,
            )

    def disconnect(
        self, profile_id: UUID, connection_id: UUID, generation: int, revision: int
    ) -> DisconnectProgress:
        """Persist a dispatch fence before cancellation; stale confirmations do nothing."""
        with self._lock:
            info = self.disconnect_info(profile_id, connection_id)
            if info.generation != generation or info.revision != revision:
                raise ProviderConnectionError("provider_confirmation_changed")
            record = self._record(profile_id, connection_id)
            if record.lifecycle != "connected":
                raise ProviderConnectionError("provider_request_refused")
            fenced = record.model_copy(
                update={
                    "lifecycle": "disconnecting",
                    "generation": record.generation + 1,
                }
            )
            self._save(
                profile_id,
                [
                    fenced if row.connection_id == connection_id else row
                    for row in self._records(profile_id)
                ],
            )
            for adapter in self.adapters:
                adapter.fence_connection(profile_id, connection_id)
        result = self.retry_cleanup(profile_id, connection_id)
        if result.status == "disconnecting":
            self.controllers.continue_cleanup(profile_id, connection_id)
        return result

    def retry_cleanup(
        self, profile_id: UUID, connection_id: UUID
    ) -> DisconnectProgress:
        """Reconcile native stop, then erase only this connection's local token copies."""
        with self._lock:
            record = self._record(profile_id, connection_id)
            if record.lifecycle == "connected" or self.controllers is None:
                raise ProviderConnectionError("provider_request_refused")
        try:
            stopped = self.controllers.stop(profile_id, connection_id)
            if not stopped:
                return DisconnectProgress(
                    connection_id=connection_id, status="disconnecting"
                )
            with self._lock:
                if any(
                    adapter.unsettled(profile_id, connection_id)
                    for adapter in self.adapters
                ):
                    return DisconnectProgress(
                        connection_id=connection_id, status="disconnecting"
                    )
            self.adapter(record.provider).erase_revision(profile_id, record)
            with self._lock:
                current = self._record(profile_id, connection_id)
                if current != record:
                    raise ProviderConnectionError("provider_connection_changed")
                self._save(
                    profile_id,
                    [
                        row
                        for row in self._records(profile_id)
                        if row.connection_id != connection_id
                    ],
                )
            return DisconnectProgress(connection_id=connection_id, status="removed")
        except (OSError, AuthError, ProviderConnectionError):
            with self._lock:
                rows = self._records(profile_id)
                if not any(row.connection_id == connection_id for row in rows):
                    return DisconnectProgress(
                        connection_id=connection_id, status="removed"
                    )
                self._save(
                    profile_id,
                    [
                        (
                            row.model_copy(update={"lifecycle": "cleanup_required"})
                            if row.connection_id == connection_id
                            else row
                        )
                        for row in rows
                    ],
                )
            return DisconnectProgress(
                connection_id=connection_id, status="cleanup_required"
            )

    def list(self, profile_id: UUID) -> list[ConnectionSummary]:
        """Observe safe rows; native summaries run outside the shared admission lock."""
        with self._lock:
            snapshot = self._records(profile_id)
        native = {
            record.connection_id: (
                record,
                self.adapter(record.provider).summary(profile_id, record),
            )
            for record in snapshot
            if self.adapter(record.provider).summary_outside_lock
        }
        with self._lock:
            rows = []
            for record in self._records(profile_id):
                adapter = self.adapter(record.provider)
                if adapter.summary_outside_lock:
                    observed = native.get(record.connection_id)
                    if observed and observed[0] == record:
                        rows.append(observed[1])
                    else:
                        rows.append(
                            ConnectionSummary(
                                provider=record.provider,
                                method=record.method,
                                connection_id=record.connection_id,
                                label=record.label,
                                generation=record.generation,
                                lifecycle=record.lifecycle,
                                auth_state="unavailable",
                            )
                        )
                else:
                    rows.append(adapter.summary(profile_id, record))
            return rows

    def cancel_profile(self, profile_id: UUID) -> None:
        """Fence all provider attempts for the profile that signed out."""
        with self._lock:
            for adapter in self.adapters:
                adapter.cancel_profile(profile_id)

    def check_lease(self, lease_hash: str) -> None:
        """Refuse a logged-out browser without changing saved provider records."""
        with self._lock:
            if self._closing or lease_hash in self.revoked_leases:
                raise ProviderConnectionError("provider_session_required")

    def cancel_lease(self, lease_hash: str) -> None:
        """Revoke an opaque lease and fence every provider's late completion."""
        with self._lock:
            self.revoked_leases.add(lease_hash)
            for adapter in self.adapters:
                adapter.cancel_lease(lease_hash)

    def begin(self, profile_id, redirect_uri, connection_id=None, *, lease_hash=""):
        """Dispatch explicit Codex sign-in to its provider owner."""
        return self.codex.begin(
            profile_id, redirect_uri, connection_id, lease_hash=lease_hash
        )

    def complete(self, profile_id, callback, *, lease_hash="", **verification):
        """Dispatch a Codex callback without interpreting provider credentials."""
        return self.codex.complete(
            profile_id, callback, lease_hash=lease_hash, **verification
        )

    def borrow(self, profile_id, connection_id, generation):
        """Borrow through the admitted connection's concrete provider."""
        with self._lock:
            record = self.admitted(profile_id, connection_id, generation)
        return self.adapter(record.provider).borrow(
            profile_id, connection_id, generation
        )

    def progress(self, profile_id, attempt_id):
        """Read a receipt from the adapter that owns its opaque attempt ID."""
        for adapter in self.adapters:
            if adapter.has_attempt(attempt_id):
                return adapter.progress(profile_id, attempt_id)
        raise ProviderConnectionError("provider_login_expired")

    def cancel(self, profile_id, attempt_id):
        """Fence an attempt through its owner, without changing saved credentials."""
        for adapter in self.adapters:
            if adapter.has_attempt(attempt_id):
                return adapter.cancel(profile_id, attempt_id)
        raise ProviderConnectionError("provider_login_expired")

    def adapter(self, provider):
        """Resolve the concrete capability without selecting another harness."""
        for adapter in self.adapters:
            if adapter.provider == provider:
                return adapter
        raise ProviderConnectionError("provider_method_unavailable")

    def login_in_progress(self, profile_id):
        """Observe all providers under the one existing lifecycle lock."""
        with self._lock:
            return any(
                adapter.login_in_progress(profile_id) for adapter in self.adapters
            )

    def _finish_close(self, workers):
        """Release custody only after fenced workers settle, including delayed cleanup."""
        for worker in workers:
            worker.join()
        with self._lock:
            if self._ownership is not None:
                self._ownership.__exit__(None, None, None)
                self._ownership = None

    def _reconcile_stores(self) -> None:
        """Scrub crash-left staging and superseded vaults; never replay sign-in.

        Unreadable admission metadata prevents cleanup and startup, rather than
        guessing that saved credentials are unowned. Only canonical UUID vaults
        and this owner's pending directories are considered.
        """
        for profile in self.root.iterdir():
            if not profile.is_dir():
                continue
            try:
                profile_id = UUID(profile.name)
                if str(profile_id) != profile.name:
                    continue
            except ValueError:
                continue
            active = {record.credential_id for record in self._records(profile_id)}
            for vault in profile.iterdir():
                if not vault.is_dir():
                    continue
                try:
                    vault_id = UUID(vault.name.removeprefix("pending-"))
                except ValueError:
                    continue
                adapter = next(
                    adapter for adapter in self.adapters if adapter.owns(vault)
                )
                adapter.reconcile_orphan(
                    vault,
                    active=not vault.name.startswith("pending-") and vault_id in active,
                )

    def _profile(self, profile_id: UUID) -> Path:
        """Resolve only a canonical profile identifier below the private root."""
        if self._ownership is None or self._closing:
            raise ProviderConnectionError("provider_connections_unavailable")
        profile_id = UUID(str(profile_id))
        path = self.root / str(profile_id)
        path.mkdir(exist_ok=True, mode=0o700)
        _restrict_windows_directory(path)
        return path

    def _records(self, profile_id: UUID) -> list[ConnectionRecord]:
        """Read committed metadata; malformed state is a read error, never empty."""
        path = self._profile(profile_id) / "connections.json"
        if not path.exists():
            return []
        try:
            return ConnectionIndex.model_validate_json(
                path.read_text(encoding="utf-8")
            ).connections
        except (OSError, ValueError):
            raise ProviderConnectionError("provider_connections_unavailable") from None

    def _save(self, profile_id: UUID, records: list[ConnectionRecord]) -> None:
        """Atomically publish the typed admission index after private staging."""
        _atomic_private(
            self._profile(profile_id) / "connections.json",
            ConnectionIndex(connections=records).model_dump(mode="json"),
        )

    def _record(self, profile_id: UUID, connection_id: UUID) -> ConnectionRecord:
        """Refuse absent or foreign bindings without consulting another profile."""
        for record in self._records(profile_id):
            if record.connection_id == connection_id:
                return record
        raise ProviderConnectionError("provider_connection_unavailable")
