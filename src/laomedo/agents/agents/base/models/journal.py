"""Journal values owned by the shared Agent capability."""

from laomedo.agents.agents.base.models.credentials import CredentialBinding
from laomedo.agents.agents.base.models.runtime import (
    RuntimeBinding,
    RuntimeCleanupReport,
)
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, model_validator


class JournalEntry(BaseModel):
    """Common journal identity; operation subclasses constrain shared fields."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    attempt_id: str = Field(
        min_length=1, description="Owning admitted attempt identity."
    )
    extensions: dict[str, JsonValue] = Field(
        default_factory=dict,
        repr=False,
        description="Detached provider-native metadata, not shared record updates.",
    )

    @model_validator(mode="after")
    def reject_shared_updates(self):
        """Native extensions cannot override shared state or operation fields."""
        reserved = {
            "status",
            "cancel_requested",
            "cancel_confirmed",
            "snapshot_ready",
            "post_run_hash",
            "output_ref",
            "error_category",
        }
        if (reserved | set(type(self).model_fields)) & self.extensions.keys():
            raise ValueError("reserved_journal_extension")
        return self


class OwnershipEntry(JournalEntry):
    """Persist exact ownership before native allocation."""

    name: str = Field(min_length=1, description="Exact admitted container name.")
    docker_endpoint: str = Field(min_length=1, description="Pinned owning daemon.")
    token: SecretStr = Field(
        exclude=True,
        repr=False,
        description="Host ownership token, explicitly projected privately.",
    )
    receipt: Path | None = Field(
        default=None, repr=False, description="Private native receipt when admitted."
    )


class NativeSessionEntry(JournalEntry):
    """Bind a real conversation before dispatch; never a host placeholder."""

    native_session: str = Field(
        min_length=1, description="Actual native conversation identity."
    )
    communication_protocol: str = Field(
        description="Observed native communication protocol."
    )


class DispatchEntry(JournalEntry):
    """Reserve or mark one exact host turn."""

    turn_id: str = Field(
        min_length=1, description="Reserved host/native turn identity."
    )


class TurnEntry(JournalEntry):
    """Native turn facts; provider-specific receipt fields remain extensions."""

    turn_id: str = Field(min_length=1, description="Observed native turn identity.")
    status: str = Field(
        description="Original native turn status, not run-state mutation."
    )


class LeaseEntry(JournalEntry):
    """Bind supervision and grant identity without transporting a live lease."""

    lease_instance: str = Field(description="Admitted supervisor instance identity.")
    grant_id: str | None = Field(
        description="Native mediation grant identity when present."
    )


class RuntimeIdentityEntry(JournalEntry):
    """Persist canonical runtime and public credential identities."""

    binding: RuntimeBinding = Field(description="Admitted native runtime fingerprint.")
    credential: CredentialBinding | None = Field(
        description="Public credential identity, or existing native null."
    )


class CorrectionEntry(JournalEntry):
    """Record correction ordering without mutating terminal run status."""

    turn_id: str = Field(min_length=1, description="Next reserved correction turn.")


class EvidenceEntry(JournalEntry):
    """Native capture metadata; shared terminal-state fields are prohibited."""


class ScopeCleanupEntry(JournalEntry):
    """Persist exact scope cleanup independently from native terminal result."""

    scope_id: str = Field(description="Single runtime scope identity.")
    report: RuntimeCleanupReport = Field(
        description="Controller and owned resource observations."
    )
