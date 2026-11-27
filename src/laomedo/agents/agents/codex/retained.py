"""Operational custody of saved token-sharing revisions pending explicit replacement.

This module cannot begin or complete sign-in. Remove it after all retained saved
revisions have been replaced or disconnected; graph exports do not require it.
"""

import hashlib
import json
import re
import time
from uuid import UUID
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import ConnectionSummary
from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import _locked


class CodexRetainedCredentials:
    """Borrow or erase only already-admitted token-sharing credentials."""

    def __init__(self, service):
        self.service = service

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

    def erase_revision(self, profile_id, record):
        """Erase the admitted retired revision under its broker refresh lock."""
        self._scrub(self._broker(profile_id, record.credential_id), record.client_id)

    def _scrub(self, broker: ChatGPTConnection, client_id: str) -> None:
        """Remove an unadmitted or superseded token file under its refresh lock.

        Do not remotely revoke a grant that may also back a committed revision.
        Controllers holding the old broker fail their next authorization probe.
        """
        with _locked(broker.lock_path):
            broker._path(client_id).unlink(missing_ok=True)

    def _broker(self, profile_id: UUID, credential_id: UUID) -> ChatGPTConnection:
        """Open only this connection's private broker, outside tool mounts."""
        return ChatGPTConnection(self.service._profile(profile_id) / str(credential_id))
