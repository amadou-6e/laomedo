"""Exact-owner login staging and atomic admission for Codex connections."""

import hashlib
import json
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
)
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.models import (
    ConnectionRecord,
    ConnectionIndex,
    ConnectionSummary,
    LoginProgress,
    PendingLogin,
)
from laomedo.host.provider_connections.settings import ATTEMPT_SECONDS, MAX_CONNECTIONS


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
        self._attempts: dict[UUID, PendingLogin] = {}

    def _profile(self, profile_id: UUID) -> Path:
        """Resolve only a canonical profile identifier below the private root."""
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

    def _broker(self, profile_id: UUID, credential_id: UUID) -> ChatGPTConnection:
        """Open only this connection's private broker, outside tool mounts."""
        return ChatGPTConnection(self._profile(profile_id) / str(credential_id))

    def list(self, profile_id: UUID) -> list[ConnectionSummary]:
        """Observe safe saved rows without refresh, login or an inference request."""
        with self._lock:
            rows = []
            for record in self._records(profile_id):
                state = "unavailable"
                try:
                    account = self._broker(profile_id, record.credential_id).account(
                        record.client_id
                    )
                    if account["generation"] == record.generation:
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
                self._record(profile_id, connection_id) if connection_id else None
            )
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
        ]
        for key in terminal[:-64]:
            del self._attempts[key]

    def progress(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Read only this profile's attempt; polling has no authentication effect."""
        with self._lock:
            self._expire()
            item = self._attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            return item.progress.model_copy()

    def cancel(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Fence a pending exchange before returning; a late result cannot commit."""
        with self._lock:
            self.progress(profile_id, attempt_id)
            item = self._attempts[attempt_id]
            if item.progress.status in {"connecting", "verifying"}:
                item.progress.status = "cancelled"
            return item.progress.model_copy()

    def cancel_profile(self, profile_id: UUID) -> None:
        """Invalidate pending native returns when this profile signs out or switches."""
        with self._lock:
            for item in self._attempts.values():
                if item.profile_id == profile_id and item.progress.status in {
                    "connecting",
                    "verifying",
                }:
                    item.progress.status = "cancelled"

    def cancel_lease(self, lease_hash: str) -> None:
        """Fence an outgoing browser session without reading its raw credential."""
        with self._lock:
            for item in self._attempts.values():
                if item.lease_hash == lease_hash and item.progress.status in {
                    "connecting",
                    "verifying",
                }:
                    item.progress.status = "cancelled"

    def complete(
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
                    return item.progress.model_copy()
                records = self._records(profile_id)
                subject_hash = hashlib.sha256(
                    (
                        staged_account["issuer"] + "\0" + staged_account["subject"]
                    ).encode()
                ).hexdigest()
                duplicate = next(
                    (
                        record
                        for record in records
                        if record.subject_hash == subject_hash
                        and record.connection_id != item.candidate_id
                    ),
                    None,
                )
                if duplicate:
                    item.progress.status = "duplicate"
                    item.progress.connection_id = duplicate.connection_id
                    return item.progress.model_copy()
                if item.previous:
                    current = self._record(profile_id, item.candidate_id)
                    if current != item.previous:
                        raise ProviderConnectionError("provider_connection_changed")
                    if subject_hash != current.subject_hash:
                        raise ProviderConnectionError("provider_account_mismatch")
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
                return item.progress.model_copy()
        except (AuthError, ProviderConnectionError):
            with self._lock:
                if item.progress.status == "verifying":
                    item.progress.status = "failed"
                    item.progress.code = "provider_sign_in_failed"
                return item.progress.model_copy()
        finally:
            # Erase the private staging copy even after cancellation or duplicate
            # admission. Revoking it here could revoke the newly committed grant.
            if staged_account is not None:
                stage._path(staged_account["client_id"]).unlink(missing_ok=True)

    def borrow(
        self, profile_id: UUID, connection_id: UUID, generation: int
    ) -> tuple[str, dict]:
        """Borrow exactly one admitted generation; never substitute another login."""
        with self._lock:
            record = self._record(profile_id, connection_id)
            if record.generation != generation:
                raise ProviderConnectionError("provider_connection_changed")
            token, identity = self._broker(
                profile_id, record.credential_id
            ).access_token(record.client_id)
            if identity["generation"] != generation:
                updated = record.model_copy(
                    update={"generation": identity["generation"]}
                )
                records = [
                    updated if item.connection_id == connection_id else item
                    for item in self._records(profile_id)
                ]
                self._save(profile_id, records)
            return token, identity
