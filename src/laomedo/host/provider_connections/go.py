"""Independent custody of explicitly supplied OpenCode Go subscription keys."""

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr

from laomedo.agents.agents.opencode.utils import check_auth_fresh
from laomedo.agents.errors import RunnerError
from laomedo.host.credentials.siwc.utils import _atomic_private
from laomedo.host.credentials.siwc.utils import _restrict_windows_directory
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.models import ConnectionRecord
from laomedo.host.provider_connections.models import ConnectionSummary


class GoConnection:
    """Keep one key per private revision; never borrow an ambient Console login.

    Keys carry no verified account identity. Exact repeated keys are detected;
    different keys for the same upstream account cannot be deduplicated here.
    Saving performs no inference and does not claim that the key is valid upstream.
    """

    def __init__(self, service):
        """Reuse the profile owner's admission lock, index and private root."""
        self.service = service

    def save(self, profile_id, key: SecretStr, label: str, *, lease_hash: str = ""):
        """Atomically save a fresh independent Go key after explicit user submission.

        Return a safe row and duplicate flag. Empty, oversized or multiline keys
        are refused. An uncertain index write is read back before cleanup; a
        possibly committed key is retained rather than silently destroyed.
        """
        value = key.get_secret_value()
        if (
            not value
            or len(value) > 8192
            or any(character.isspace() for character in value)
        ):
            raise ProviderConnectionError("provider_request_refused")
        label = label.strip()
        if not label or len(label) > 100:
            raise ProviderConnectionError("provider_request_refused")
        digest = hashlib.sha256(value.encode()).hexdigest()
        with self.service._lock:
            if lease_hash in self.service.revoked_leases:
                raise ProviderConnectionError("provider_session_required")
            records = self.service._records(profile_id)
            for record in records:
                if record.provider == "opencode" and record.subject_hash == digest:
                    return self.summary(profile_id, record), True
            from laomedo.host.provider_connections.settings import MAX_CONNECTIONS

            if len(records) >= MAX_CONNECTIONS:
                raise ProviderConnectionError("provider_connection_limit")
            record = ConnectionRecord(
                provider="opencode",
                connection_id=uuid4(),
                credential_id=uuid4(),
                client_id="opencode-go",
                subject_hash=digest,
                generation=1,
                label=label,
            )
            root = self.service._profile(profile_id) / str(record.credential_id)
            root.mkdir(mode=0o700)
            _restrict_windows_directory(root)
            # The marker precedes any secret, so startup can reconcile a crash
            # before the admission index is published.
            _atomic_private(root / "go-custody.json", {"provider": "opencode-go"})
            try:
                _atomic_private(
                    root / "auth.json", {"opencode-go": {"type": "api", "key": value}}
                )
                _atomic_private(
                    root / "auth-validity.json",
                    {
                        "credential_mode": "provider_key",
                        "credential_sha256": digest,
                        "expires_at_ms": None,
                    },
                )
                self.service._save(profile_id, [*records, record])
            except Exception:
                # A failed atomic publication can still have committed. An
                # unreadable index keeps custody for explicit reconciliation.
                committed = self.service._records(profile_id)
                if record not in committed:
                    self.erase(root)
                    raise ProviderConnectionError("provider_save_unconfirmed") from None
            return self.summary(profile_id, record), False

    def profile(self, profile_id, record: ConnectionRecord) -> Path:
        """Resolve and validate only the exact admitted Go credential revision."""
        if record.provider != "opencode" or record.client_id != "opencode-go":
            raise ProviderConnectionError("provider_connection_unavailable")
        root = self.service._profile(profile_id) / str(record.credential_id)
        try:
            check_auth_fresh(root)
            validity = json.loads(
                (root / "auth-validity.json").read_text(encoding="utf-8")
            )
            if validity["credential_sha256"] != record.subject_hash:
                raise ValueError()
        except (RunnerError, OSError, ValueError, KeyError):
            raise ProviderConnectionError("provider_connection_unavailable") from None
        return root

    def summary(self, profile_id, record: ConnectionRecord) -> ConnectionSummary:
        """Report local key custody; unavailable means upstream auth is unverified."""
        state = "unavailable"
        try:
            self.profile(profile_id, record)
        except ProviderConnectionError:
            state = "revoked"
        return ConnectionSummary(
            provider="opencode",
            method="opencode_go_key",
            connection_id=record.connection_id,
            label=record.label,
            generation=record.generation,
            auth_state=state,
            lifecycle=record.lifecycle,
        )

    @staticmethod
    def erase(root: Path) -> None:
        """Remove fixed credential files only after the caller confirms native stop."""
        for name in (
            "auth.json",
            "auth-validity.json",
            "credential-binding-key",
            "go-custody.json",
        ):
            (root / name).unlink(missing_ok=True)
            for pending in root.glob(name + ".pending-*"):
                if re.fullmatch(
                    re.escape(name) + r"\.pending-[0-9a-f]{32}", pending.name
                ):
                    pending.unlink()
