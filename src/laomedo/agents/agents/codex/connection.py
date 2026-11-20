"""Codex-owned sign-in staging, publication and credential revision lifecycle."""

import hashlib
import json
import logging
import re
import secrets
import time
from pathlib import Path
from uuid import UUID, uuid4
from pydantic import SecretStr
from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import _atomic_private, _locked
from laomedo.agents.connections.base import BaseProviderConnection
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import (
    ConnectionRecord,
    ConnectionSummary,
    LoginProgress,
)
from laomedo.agents.connections.settings import ATTEMPT_SECONDS, MAX_CONNECTIONS
from laomedo.agents.agents.codex.models import PendingLogin
from laomedo.agents.agents.codex.settings import LOGIN_FAILURE_CATEGORIES


class CodexConnection(BaseProviderConnection):
    """Own app sign-in without changing shared owner/generation admission."""

    provider = "codex"

    def __init__(self, service):
        """Use the existing lifecycle lock and own only Codex attempt state."""
        self.service = service
        self.attempts: dict[UUID, PendingLogin] = {}

    def begin(
        self,
        profile_id: UUID,
        redirect_uri: str,
        connection_id: UUID | None = None,
        *,
        lease_hash: str = "",
    ) -> tuple[LoginProgress, str]:
        """Prepare one explicit sign-in; only the caller opens the returned URL."""
        with self.service._lock:
            self._expire()
            if self.service.login_in_progress(profile_id):
                raise ProviderConnectionError("provider_login_in_progress")
            records = self.service._records(profile_id)
            if connection_id is None and len(records) >= MAX_CONNECTIONS:
                raise ProviderConnectionError("provider_connection_limit")
            previous = (
                self.service.admitted(profile_id, connection_id)
                if connection_id
                else None
            )
            if previous is not None and previous.provider != "codex":
                raise ProviderConnectionError("provider_method_unavailable")
            if (
                previous
                and self.service.controllers is not None
                and self.service.controllers.inventory(profile_id, connection_id)[0]
            ):
                raise ProviderConnectionError("provider_connection_busy")
            candidate = connection_id or uuid4()
            attempt_id = uuid4()
            stage = self.service._profile(profile_id) / ("pending-" + str(attempt_id))
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
            self.attempts[attempt_id] = PendingLogin(
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

    def progress(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Read only this profile's attempt; polling has no authentication effect."""
        with self.service._lock:
            self._expire()
            item = self.attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if item.progress.code == "provider_save_unconfirmed":
                self._reconcile_publication(item)
        return self._settle(profile_id, attempt_id)

    def cancel(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Fence a pending exchange before returning; a late result cannot commit."""
        with self.service._lock:
            self._expire()
            item = self.attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if item.progress.status in {"connecting", "verifying"}:
                item.progress.status = "cancelled"
            return item.progress.model_copy()

    def complete(
        self, profile_id: UUID, callback: dict, *, lease_hash: str = "", **verification
    ) -> LoginProgress:
        """Return a detached receipt only after the private exchange and cleanup settle."""
        result = self._complete(
            profile_id, callback, lease_hash=lease_hash, **verification
        )
        return self._settle(profile_id, result.attempt_id)

    def borrow(
        self, profile_id: UUID, connection_id: UUID, generation: int
    ) -> tuple[str, dict]:
        """Borrow exactly one admitted generation; never substitute another login."""
        with self.service._lock:
            record = self.service.admitted(profile_id, connection_id, generation)
            if record.provider != "codex":
                raise ProviderConnectionError("provider_method_unavailable")
            broker = self._broker(profile_id, record.credential_id)
        # Token rotation has its own broker lock/counter. It must not block
        # unrelated logout/cancellation or change the stable connection epoch.
        token, identity = broker.access_token(record.client_id)
        with self.service._lock:
            if self.service.admitted(profile_id, connection_id, generation) != record:
                raise ProviderConnectionError("provider_connection_changed")
            identity = {
                **identity,
                "connection_generation": record.generation,
                "credential_generation": identity["generation"],
            }
            return token, identity

    def has_attempt(self, attempt_id):
        """Identify Codex receipts without starting login."""
        return attempt_id in self.attempts

    def login_in_progress(self, profile_id):
        """Keep the original active-receipt sign-in guard."""
        return any(
            item.profile_id == profile_id
            and item.progress.status in {"connecting", "verifying"}
            for item in self.attempts.values()
        )

    def unsettled(self, profile_id, connection_id):
        """Retain custody until callback exchange and staging cleanup settle."""
        return any(
            item.profile_id == profile_id
            and item.candidate_id == connection_id
            and item.exchanging
            for item in self.attempts.values()
        )

    def fence_all(self):
        """Fence late callbacks during service shutdown."""
        for item in self.attempts.values():
            if item.progress.status in {"connecting", "verifying"}:
                item.progress.status = "cancelled"

    def cancel_profile(self, profile_id):
        """Fence only the signing-out profile's active attempts."""
        for item in self.attempts.values():
            if item.profile_id == profile_id and item.progress.status in {
                "connecting",
                "verifying",
            }:
                item.progress.status = "cancelled"

    def cancel_lease(self, lease_hash):
        """Fence only attempts belonging to the revoked opaque lease."""
        for item in self.attempts.values():
            if item.lease_hash == lease_hash and item.progress.status in {
                "connecting",
                "verifying",
            }:
                item.progress.status = "cancelled"

    def fence_connection(self, profile_id, connection_id):
        """Fence pending exchanges for a disconnecting connection."""
        for item in self.attempts.values():
            if (
                item.profile_id == profile_id
                and item.candidate_id == connection_id
                and item.progress.status in {"connecting", "verifying"}
            ):
                item.progress.status = "cancelled"

    def owns(self, vault):
        """Retain Codex fallback ownership after marked native stores are checked."""
        return True

    def reconcile_orphan(self, vault, active=False):
        """Clean exact Codex staging writes without guessing admission ownership."""
        broker = ChatGPTConnection(vault)
        with _locked(broker.lock_path):
            for pending in broker.accounts.glob("*.json.pending-*"):
                if re.fullmatch(
                    r"[0-9a-f]{64}\.json\.pending-[0-9a-f]{32}", pending.name
                ):
                    pending.unlink()
        if active:
            return
        for path in broker.accounts.glob("*.json"):
            account = json.loads(path.read_text(encoding="utf-8"))
            client_id = account["client_id"]
            if broker._path(client_id) != path:
                raise ProviderConnectionError("provider_cleanup_unconfirmed")
            self._scrub(broker, client_id)

    def erase_revision(self, profile_id, record):
        """Erase settled staging and all locally retained revisions of this account."""
        with self.service._lock:
            attempts = [
                item
                for item in self.attempts.values()
                if item.profile_id == profile_id
                and item.candidate_id == record.connection_id
            ]
            revisions = {
                entry.credential_id: entry
                for item in attempts
                for entry in (item.previous, item.publication)
                if entry is not None
            }
            revisions[record.credential_id] = record
        for item in attempts:
            self._discard_stage(item)
        for entry in revisions.values():
            self._scrub(self._broker(profile_id, entry.credential_id), entry.client_id)

    def summary(self, profile_id, record):
        """Read native account status without refresh or a model request."""
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
        return ConnectionSummary(
            connection_id=record.connection_id,
            label=record.label,
            generation=record.generation,
            auth_state=state,
            lifecycle=record.lifecycle,
        )

    def check_attempt(self, profile_id, attempt_id, lease_hash):
        """Verify the exact owner and opaque originating lease under the service lock."""
        item = self.attempts.get(attempt_id)
        if (
            item is None
            or item.profile_id != profile_id
            or item.lease_hash != lease_hash
        ):
            raise ProviderConnectionError("provider_login_expired")

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

    def _broker(self, profile_id: UUID, credential_id: UUID) -> ChatGPTConnection:
        """Open only this connection's private broker, outside tool mounts."""
        return ChatGPTConnection(self.service._profile(profile_id) / str(credential_id))

    def _expire(self) -> None:
        """Fence expired attempts; keep a bounded set of safe terminal receipts."""
        for item in self.attempts.values():
            if (
                item.progress.status in {"connecting", "verifying"}
                and item.expires_at <= time.monotonic()
            ):
                item.progress.status = "expired"
        terminal = [
            key
            for key, item in self.attempts.items()
            if item.progress.status not in {"connecting", "verifying"}
            and not item.exchanging
        ]
        for key in terminal[:-64]:
            del self.attempts[key]

    def _settle(self, profile_id: UUID, attempt_id: UUID) -> LoginProgress:
        """Clean superseded tokens outside the global lifecycle lock before copying a receipt."""
        with self.service._lock:
            item = self.attempts[attempt_id]
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
                with self.service._lock:
                    item.superseded_scrubbed = True
            except (OSError, AuthError, ProviderConnectionError):
                with self.service._lock:
                    item.progress.status = "failed"
                    item.progress.code = "provider_save_unconfirmed"
        with self.service._lock:
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
            records = self.service._records(item.profile_id)
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

    def _complete(
        self, profile_id: UUID, callback: dict, *, lease_hash: str = "", **verification
    ) -> LoginProgress:
        """Consume a matching callback once, verify privately and fence before commit.

        Network exchange occurs outside the lifecycle lock so cancellation can
        win while the provider is slow. Staged credentials are never borrowable.
        Optional verifier arguments are used only by concern-owned tests.
        """
        with self.service._lock:
            self._expire()
            candidates = [
                item
                for item in self.attempts.values()
                if item.profile_id == profile_id
                and secrets.compare_digest(item.lease_hash, lease_hash)
                and item.progress.status == "connecting"
                and secrets.compare_digest(
                    json.loads(item.oauth.get_secret_value())["state"].encode(),
                    str(callback.get("state", "")).encode("utf-8", errors="replace"),
                )
            ]
            if len(candidates) != 1:
                logging.getLogger(__name__).warning(
                    "Codex callback refused: phase=binding candidates=%d profile_attempts=%d lease_matches=%d state_matches=%d",
                    len(candidates),
                    sum(
                        item.profile_id == profile_id for item in self.attempts.values()
                    ),
                    sum(
                        item.profile_id == profile_id
                        and secrets.compare_digest(item.lease_hash, lease_hash)
                        for item in self.attempts.values()
                    ),
                    sum(
                        item.profile_id == profile_id
                        and secrets.compare_digest(
                            json.loads(item.oauth.get_secret_value())["state"].encode(),
                            str(callback.get("state", "")).encode(
                                "utf-8", errors="replace"
                            ),
                        )
                        for item in self.attempts.values()
                    ),
                )
                raise ProviderConnectionError("provider_login_expired")
            item = candidates[0]
            item.progress.status = "verifying"
            item.exchanging = True
            oauth = json.loads(item.oauth.get_secret_value())
        stage = ChatGPTConnection(item.stage)
        staged_account = None
        phase = "exchange_and_verification"
        try:
            stage.finish(oauth, callback, **verification)
            client_id = callback.get("client_id") or oauth["client_id"]
            staged_account = stage.account(client_id)
            phase = "admission"
            with self.service._lock:
                self._expire()
                if item.progress.status != "verifying":
                    return item.progress
                records = self.service._records(profile_id)
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
                        if record.provider == "codex"
                        and record.connection_id != item.candidate_id
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
                    current = self.service.admitted(profile_id, item.candidate_id)
                    if current != item.previous:
                        raise ProviderConnectionError("provider_connection_changed")
                    if subject_hash != current.subject_hash:
                        raise ProviderConnectionError("provider_account_mismatch")
                    if (
                        self.service.controllers is not None
                        and self.service.controllers.inventory(
                            profile_id, item.candidate_id
                        )[0]
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
                phase = "publication"
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
                self.service._save(profile_id, records)
                item.progress.status = "connected"
                item.progress.connection_id = item.candidate_id
                return item.progress
        except Exception as failure:
            category = getattr(failure, "code", None)
            safe_category = (
                category
                if isinstance(category, str)
                and (
                    category in LOGIN_FAILURE_CATEGORIES
                    or re.fullmatch(r"auth_http_[1-5][0-9]{2}", category)
                )
                else "unclassified"
            )
            logging.getLogger(__name__).warning(
                "Codex sign-in failed: phase=%s category=%s exception_type=%s",
                phase,
                safe_category,
                type(failure).__name__,
            )
            with self.service._lock:
                if item.publication is not None:
                    try:
                        self._reconcile_publication(item)
                    except (OSError, AuthError):
                        item.progress.status = "failed"
                        item.progress.code = "provider_save_unconfirmed"
                elif item.progress.status == "verifying":
                    item.progress.status = "failed"
                    item.progress.code = (
                        "provider_account_mismatch"
                        if isinstance(failure, (AuthError, ProviderConnectionError))
                        and category
                        in {"auth_account_mismatch", "provider_account_mismatch"}
                        else "provider_sign_in_failed"
                    )
                return item.progress
        finally:
            # Erase the private staging copy even after cancellation or duplicate
            # admission. Revoking it here could revoke the newly committed grant.
            try:
                self._discard_stage(item)
            except (OSError, AuthError):
                with self.service._lock:
                    item.progress.status = "failed"
                    item.progress.code = "provider_save_unconfirmed"
            finally:
                with self.service._lock:
                    item.exchanging = False
