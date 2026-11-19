"""Exact-owner login staging and atomic admission for Codex connections."""

import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import SecretStr

from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import (
    _atomic_private,
    _outside_git,
    _restrict_windows_directory,
    _locked,
)
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.go import GoConnection
from laomedo.host.provider_connections.claude import ClaudeConnection
from laomedo.host.provider_connections.models import (
    GraphProviderPreferences,
    ConnectionRecord,
    ConnectionIndex,
    ConnectionSummary,
    LoginProgress,
    PendingLogin,
    DisconnectInfo,
    DisconnectProgress,
)
from laomedo.host.provider_connections.settings import (
    ATTEMPT_SECONDS,
    MAX_CONNECTIONS,
    NATIVE_AUTH_CLEANUP_SECONDS,
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
        self.go = GoConnection(self)
        self.claude = ClaudeConnection(self)
        self._attempts: dict[UUID, PendingLogin] = {}
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
            for item in self.claude.attempts.values():
                item.cancelled.set()
            for item in self._attempts.values():
                if item.progress.status in {"connecting", "verifying"}:
                    item.progress.status = "cancelled"
            workers = [
                item.worker for item in self.claude.attempts.values() if item.worker
            ]
        deadline = time.monotonic() + NATIVE_AUTH_CLEANUP_SECONDS
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

    def _finish_close(self, workers):
        """Release custody only after fenced workers settle, including delayed cleanup."""
        for worker in workers:
            worker.join()
        with self._lock:
            if self._ownership is not None:
                self._ownership.__exit__(None, None, None)
                self._ownership = None

    def _scrub(self, broker: ChatGPTConnection, client_id: str) -> None:
        """Remove an unadmitted or superseded token file under its refresh lock.

        Do not remotely revoke a grant that may also back a committed revision.
        Controllers holding the old broker fail their next authorization probe.
        """
        with _locked(broker.lock_path):
            broker._path(client_id).unlink(missing_ok=True)

    def _discard_stage(self, item: PendingLogin) -> None:
        """Scrub this attempt's owned token files, including interrupted atomic writes."""
        broker = ChatGPTConnection(item.stage)
        with _locked(broker.lock_path):
            for path in broker.accounts.iterdir():
                if re.fullmatch(
                    r"[0-9a-f]{64}\.json(?:\.pending-[0-9a-f]{32})?", path.name
                ):
                    path.unlink(missing_ok=True)

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
                if (vault / "go-custody.json").exists():
                    if vault_id not in active:
                        self.go.erase(vault)
                    continue
                if (vault / "claude-custody.json").exists():
                    if vault_id not in active:
                        self.claude.reconcile_orphan(vault)
                    continue
                broker = ChatGPTConnection(vault)
                with _locked(broker.lock_path):
                    for pending in broker.accounts.glob("*.json.pending-*"):
                        if re.fullmatch(
                            r"[0-9a-f]{64}\.json\.pending-[0-9a-f]{32}", pending.name
                        ):
                            pending.unlink()
                if not vault.name.startswith("pending-") and vault_id in active:
                    continue
                for path in broker.accounts.glob("*.json"):
                    account = json.loads(path.read_text(encoding="utf-8"))
                    client_id = account["client_id"]
                    if broker._path(client_id) != path:
                        raise ProviderConnectionError("provider_cleanup_unconfirmed")
                    self._scrub(broker, client_id)

    def _profile(self, profile_id: UUID) -> Path:
        """Resolve only a canonical profile identifier below the private root."""
        if self._ownership is None or self._closing:
            raise ProviderConnectionError("provider_connections_unavailable")
        profile_id = UUID(str(profile_id))
        path = self.root / str(profile_id)
        path.mkdir(exist_ok=True, mode=0o700)
        _restrict_windows_directory(path)
        return path

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
            for item in self._attempts.values():
                if (
                    item.profile_id == profile_id
                    and item.candidate_id == connection_id
                    and item.progress.status in {"connecting", "verifying"}
                ):
                    item.progress.status = "cancelled"
            for item in self.claude.attempts.values():
                if item.profile_id == profile_id and item.candidate_id == connection_id:
                    self.claude.cancel(profile_id, item.progress.attempt_id)
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
                    item.profile_id == profile_id
                    and item.candidate_id == connection_id
                    and not item.settled
                    for item in self.claude.attempts.values()
                ):
                    return DisconnectProgress(
                        connection_id=connection_id, status="disconnecting"
                    )
                attempts = [
                    item
                    for item in self._attempts.values()
                    if item.profile_id == profile_id
                    and item.candidate_id == connection_id
                ]
                if any(item.exchanging for item in attempts):
                    return DisconnectProgress(
                        connection_id=connection_id, status="disconnecting"
                    )
                revisions = {
                    entry.credential_id: entry
                    for item in attempts
                    for entry in (item.previous, item.publication)
                    if entry is not None
                }
                revisions[record.credential_id] = record
            # A refresh admitted before the fence may still hold this broker lock.
            # Wait outside the lifecycle lock, then remove its completed copy.
            for item in attempts:
                self._discard_stage(item)
            for entry in revisions.values():
                if entry.provider == "opencode":
                    self.go.erase(self._profile(profile_id) / str(entry.credential_id))
                elif entry.provider == "claude":
                    self.claude.erase(
                        self._profile(profile_id) / str(entry.credential_id)
                    )
                else:
                    self._scrub(
                        self._broker(profile_id, entry.credential_id), entry.client_id
                    )
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

    def _broker(self, profile_id: UUID, credential_id: UUID) -> ChatGPTConnection:
        """Open only this connection's private broker, outside tool mounts."""
        return ChatGPTConnection(self._profile(profile_id) / str(credential_id))

    def list(self, profile_id: UUID) -> list[ConnectionSummary]:
        """Observe safe saved rows without refresh, login or an inference request."""
        with self._lock:
            snapshot = self._records(profile_id)
        native = {
            record.connection_id: (record, self.claude.summary(profile_id, record))
            for record in snapshot
            if record.provider == "claude"
        }
        with self._lock:
            rows = []
            for record in self._records(profile_id):
                if record.provider == "claude":
                    observed = native.get(record.connection_id)
                    if observed and observed[0] == record:
                        rows.append(observed[1])
                    else:
                        rows.append(
                            ConnectionSummary(
                                provider="claude",
                                method="claude_native",
                                connection_id=record.connection_id,
                                label=record.label,
                                generation=record.generation,
                                lifecycle=record.lifecycle,
                                auth_state="unavailable",
                            )
                        )
                    continue
                if record.provider == "opencode":
                    rows.append(self.go.summary(profile_id, record))
                    continue
                state = "unavailable"
                try:
                    account = self._broker(profile_id, record.credential_id).account(
                        record.client_id
                    )
                    if (
                        hashlib.sha256(
                            (account["issuer"] + "\0" + account["subject"]).encode()
                        ).hexdigest()
                        == record.subject_hash
                    ):
                        state = {
                            "active": "ready",
                            "revoked": "revoked",
                            "revocation_pending": "revoked",
                            "refresh_unknown": "reauthorization_required",
                            "refresh_in_flight": "reauthorization_required",
                        }.get(account["state"], "unavailable")
                        if state == "ready" and account["expires_at"] <= time.time():
                            state = "expired"
                except (AuthError, OSError, ValueError, KeyError):
                    pass
                rows.append(
                    ConnectionSummary(
                        connection_id=record.connection_id,
                        label=record.label,
                        generation=record.generation,
                        auth_state=state,
                        lifecycle=record.lifecycle,
                    )
                )
            return rows

    def begin(
        self,
        profile_id: UUID,
        redirect_uri: str,
        connection_id: UUID | None = None,
        *,
        lease_hash: str = "",
    ) -> tuple[LoginProgress, str]:
        """Prepare one explicit sign-in; only the caller opens the returned URL."""
        with self._lock:
            self._expire()
            if any(
                item.profile_id == profile_id and not item.settled
                for item in self.claude.attempts.values()
            ):
                raise ProviderConnectionError("provider_login_in_progress")
            active = [
                item
                for item in self._attempts.values()
                if item.profile_id == profile_id
                and item.progress.status in {"connecting", "verifying"}
            ]
            if active:
                raise ProviderConnectionError("provider_login_in_progress")
            records = self._records(profile_id)
            if connection_id is None and len(records) >= MAX_CONNECTIONS:
                raise ProviderConnectionError("provider_connection_limit")
            previous = (
                self.admitted(profile_id, connection_id) if connection_id else None
            )
            if previous is not None and previous.provider != "codex":
                raise ProviderConnectionError("provider_method_unavailable")
            if (
                previous
                and self.controllers is not None
                and self.controllers.inventory(profile_id, connection_id)[0]
            ):
                raise ProviderConnectionError("provider_connection_busy")
            candidate = connection_id or uuid4()
            attempt_id = uuid4()
            stage = self._profile(profile_id) / ("pending-" + str(attempt_id))
            broker = ChatGPTConnection(stage)
            # Reconnect hints are read from the exact saved broker. The staging
            # broker never replaces it during verification.
            source = (
                self._broker(profile_id, previous.credential_id) if previous else broker
            )
            oauth = source.begin(
                redirect_uri, client_id=previous.client_id if previous else None
            )
            progress = LoginProgress(attempt_id=attempt_id, status="connecting")
            self._attempts[attempt_id] = PendingLogin(
                profile_id=profile_id,
                lease_hash=lease_hash,
                candidate_id=candidate,
                oauth=SecretStr(json.dumps(oauth)),
                stage=stage,
                expires_at=time.monotonic() + ATTEMPT_SECONDS,
                previous=previous,
                progress=progress,
            )
            return progress.model_copy(), oauth["url"]

    def _expire(self) -> None:
        """Fence expired attempts; keep a bounded set of safe terminal receipts."""
        for item in self._attempts.values():
            if (
                item.progress.status in {"connecting", "verifying"}
                and item.expires_at <= time.monotonic()
            ):
                item.progress.status = "expired"
        terminal = [
            key
            for key, item in self._attempts.items()
            if item.progress.status not in {"connecting", "verifying"}
            and not item.exchanging
        ]
        for key in terminal[:-64]:
            del self._attempts[key]

    def progress(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Read only this profile's attempt; polling has no authentication effect."""
        if attempt_id in self.claude.attempts:
            return LoginProgress.model_validate(
                self.claude.details(profile_id, attempt_id)["progress"]
            )
        with self._lock:
            self._expire()
            item = self._attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if item.progress.code == "provider_save_unconfirmed":
                self._reconcile_publication(item)
        return self._settle(profile_id, attempt_id)

    def _settle(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Clean superseded tokens outside the global lifecycle lock before copying a receipt."""
        with self._lock:
            item = self._attempts[attempt_id]
            previous = (
                item.previous
                if item.progress.status == "connected" and not item.superseded_scrubbed
                else None
            )
        if previous is not None:
            try:
                self._scrub(
                    self._broker(profile_id, previous.credential_id), previous.client_id
                )
                with self._lock:
                    item.superseded_scrubbed = True
            except (OSError, AuthError, ProviderConnectionError):
                with self._lock:
                    item.progress.status = "failed"
                    item.progress.code = "provider_save_unconfirmed"
        with self._lock:
            return item.progress.model_copy()

    def _reconcile_publication(self, item: PendingLogin) -> None:
        """Read back an attempted pointer write before reporting or discarding it."""
        self._discard_stage(item)
        if item.publication is None:
            item.progress.status = "failed"
            item.progress.code = "provider_sign_in_failed"
            return
        item.progress.status = "failed"
        item.progress.code = "provider_save_unconfirmed"
        try:
            records = self._records(item.profile_id)
        except ProviderConnectionError:
            item.progress.status = "failed"
            item.progress.code = "provider_save_unconfirmed"
            return
        admitted = next(
            (record for record in records if record.connection_id == item.candidate_id),
            None,
        )
        if admitted == item.publication:
            item.progress.status = "connected"
            item.progress.connection_id = item.candidate_id
            item.progress.code = None
        else:
            self._scrub(
                self._broker(item.profile_id, item.publication.credential_id),
                item.publication.client_id,
            )
            item.progress.status = "failed"
            item.progress.code = "provider_sign_in_failed"

    def cancel(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Fence a pending exchange before returning; a late result cannot commit."""
        if attempt_id in self.claude.attempts:
            return self.claude.cancel(profile_id, attempt_id)
        with self._lock:
            self._expire()
            item = self._attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if item.progress.status in {"connecting", "verifying"}:
                item.progress.status = "cancelled"
            return item.progress.model_copy()

    def cancel_profile(self, profile_id: UUID) -> None:
        """Invalidate pending native returns when this profile signs out or switches."""
        with self._lock:
            for item in self.claude.attempts.values():
                if item.profile_id == profile_id:
                    self.claude.cancel(profile_id, item.progress.attempt_id)
            for item in self._attempts.values():
                if item.profile_id == profile_id and item.progress.status in {
                    "connecting",
                    "verifying",
                }:
                    item.progress.status = "cancelled"

    def check_lease(self, lease_hash: str) -> None:
        """Refuse a logged-out browser without changing saved provider records."""
        with self._lock:
            if self._closing or lease_hash in self.revoked_leases:
                raise ProviderConnectionError("provider_session_required")

    def cancel_lease(self, lease_hash: str) -> None:
        """Fence an outgoing browser session without reading its raw credential."""
        with self._lock:
            self.revoked_leases.add(lease_hash)
            for item in self.claude.attempts.values():
                if item.lease_hash == lease_hash:
                    self.claude.cancel(item.profile_id, item.progress.attempt_id)
            for item in self._attempts.values():
                if item.lease_hash == lease_hash and item.progress.status in {
                    "connecting",
                    "verifying",
                }:
                    item.progress.status = "cancelled"

    def complete(
        self, profile_id: UUID, callback: dict, *, lease_hash: str = "", **verification
    ) -> LoginProgress:
        """Return a detached receipt only after the private exchange and cleanup settle."""
        result = self._complete(
            profile_id, callback, lease_hash=lease_hash, **verification
        )
        return self._settle(profile_id, result.attempt_id)

    def _complete(
        self, profile_id: UUID, callback: dict, *, lease_hash: str = "", **verification
    ) -> LoginProgress:
        """Consume a matching callback once, verify privately and fence before commit.

        Network exchange occurs outside the lifecycle lock so cancellation can
        win while the provider is slow. Staged credentials are never borrowable.
        Optional verifier arguments are used only by concern-owned tests.
        """
        with self._lock:
            self._expire()
            candidates = [
                item
                for item in self._attempts.values()
                if item.profile_id == profile_id
                and secrets.compare_digest(item.lease_hash, lease_hash)
                and item.progress.status == "connecting"
                and secrets.compare_digest(
                    json.loads(item.oauth.get_secret_value())["state"],
                    str(callback.get("state", "")),
                )
            ]
            if len(candidates) != 1:
                raise ProviderConnectionError("provider_login_expired")
            item = candidates[0]
            item.progress.status = "verifying"
            item.exchanging = True
            oauth = json.loads(item.oauth.get_secret_value())
        stage = ChatGPTConnection(item.stage)
        staged_account = None
        try:
            stage.finish(oauth, callback, **verification)
            client_id = callback.get("client_id") or oauth["client_id"]
            staged_account = stage.account(client_id)
            with self._lock:
                self._expire()
                if item.progress.status != "verifying":
                    return item.progress
                records = self._records(profile_id)
                subject_hash = hashlib.sha256(
                    (
                        staged_account["issuer"] + "\0" + staged_account["subject"]
                    ).encode()
                ).hexdigest()
                email = staged_account.get("email")
                # Labels are immutable provider email projections. This rule
                # only refuses a new row; reconnect identity stays subject-bound.
                normalized_email = (
                    email.strip().casefold()
                    if isinstance(email, str) and email.strip()
                    else None
                )
                duplicate = next(
                    (
                        record
                        for record in records
                        if record.connection_id != item.candidate_id
                        and (
                            record.subject_hash == subject_hash
                            or item.previous is None
                            and normalized_email is not None
                            and record.label.strip().casefold() == normalized_email
                        )
                    ),
                    None,
                )
                if duplicate:
                    item.progress.status = "duplicate"
                    item.progress.connection_id = duplicate.connection_id
                    return item.progress
                if item.previous:
                    current = self.admitted(profile_id, item.candidate_id)
                    if current != item.previous:
                        raise ProviderConnectionError("provider_connection_changed")
                    if subject_hash != current.subject_hash:
                        raise ProviderConnectionError("provider_account_mismatch")
                    if (
                        self.controllers is not None
                        and self.controllers.inventory(profile_id, item.candidate_id)[0]
                    ):
                        raise ProviderConnectionError("provider_connection_busy")
                generation = item.previous.generation + 1 if item.previous else 1
                staged_account["generation"] = generation
                record = ConnectionRecord(
                    connection_id=item.candidate_id,
                    credential_id=uuid4(),
                    client_id=client_id,
                    subject_hash=subject_hash,
                    generation=generation,
                    label=staged_account.get("email") or "ChatGPT account",
                )
                broker = self._broker(profile_id, record.credential_id)
                item.publication = record
                _atomic_private(
                    broker.host_path,
                    {"ext_agent_host_id": staged_account["ext_agent_host_id"]},
                )
                _atomic_private(broker._path(client_id), staged_account)
                records = [
                    entry
                    for entry in records
                    if entry.connection_id != item.candidate_id
                ] + [record]
                self._save(profile_id, records)
                item.progress.status = "connected"
                item.progress.connection_id = item.candidate_id
                return item.progress
        except Exception:
            with self._lock:
                if item.publication is not None:
                    try:
                        self._reconcile_publication(item)
                    except (OSError, AuthError):
                        item.progress.status = "failed"
                        item.progress.code = "provider_save_unconfirmed"
                elif item.progress.status == "verifying":
                    item.progress.status = "failed"
                    item.progress.code = "provider_sign_in_failed"
                return item.progress
        finally:
            # Erase the private staging copy even after cancellation or duplicate
            # admission. Revoking it here could revoke the newly committed grant.
            try:
                self._discard_stage(item)
            except (OSError, AuthError):
                with self._lock:
                    item.progress.status = "failed"
                    item.progress.code = "provider_save_unconfirmed"
            finally:
                with self._lock:
                    item.exchanging = False

    def borrow(
        self, profile_id: UUID, connection_id: UUID, generation: int
    ) -> tuple[str, dict]:
        """Borrow exactly one admitted generation; never substitute another login."""
        with self._lock:
            record = self.admitted(profile_id, connection_id, generation)
            if record.provider != "codex":
                raise ProviderConnectionError("provider_method_unavailable")
            broker = self._broker(profile_id, record.credential_id)
        # Token rotation has its own broker lock/counter. It must not block
        # unrelated logout/cancellation or change the stable connection epoch.
        token, identity = broker.access_token(record.client_id)
        with self._lock:
            if self.admitted(profile_id, connection_id, generation) != record:
                raise ProviderConnectionError("provider_connection_changed")
            identity = {
                **identity,
                "connection_generation": record.generation,
                "credential_generation": identity["generation"],
            }
            return token, identity
