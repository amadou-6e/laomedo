"""Exact reservation identity; it does not grant Docker or mediation authority."""

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr
from pydantic import JsonValue
from pydantic import ValidationError
from laomedo.host.leases.settings import GRANT_TTL_SECONDS


class ContainerIdentity(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    name: str = Field(description="Exact container name reserved by the host.")
    run_id: str = Field(description="Application run owning this reservation.")
    token: SecretStr = Field(
        repr=False, exclude=True, description="Private host lease ownership label."
    )
    docker_endpoint: str | None = Field(
        default=None,
        description="Original pinned daemon endpoint; missing legacy data cannot establish cleanup.",
    )

    @classmethod
    def from_registration(cls, record):
        """Read a private lease registration without inferring a legacy endpoint."""
        return cls(
            name=record["name"],
            run_id=record["run_id"],
            token=record["token"],
            docker_endpoint=record.get("docker_endpoint"),
        )

    def client(self):
        """Open only the recorded endpoint, never the ambient default daemon."""
        if not self.docker_endpoint:
            raise ValueError("Original Docker endpoint unavailable")
        from py_docker import Client

        return Client(environment={"DOCKER_HOST": self.docker_endpoint})

    def reservation(self):
        """Project application ownership into the canonical runtime reservation."""
        from py_docker.containers.models import ContainerReservation
        from laomedo.host.leases import settings

        return ContainerReservation(
            name=self.name,
            labels={settings.LABEL_RUN: self.run_id, settings.LABEL_TOKEN: self.token},
        )

    def registration(self, *, runner_pid, created_at, mediation):
        """Explicit private IPC record, never an HTTP/Activity/log projection."""
        return {
            "name": self.name,
            "run_id": self.run_id,
            "token": self.token.get_secret_value(),
            **(
                {"docker_endpoint": self.docker_endpoint}
                if self.docker_endpoint is not None
                else {}
            ),
            "runner_pid": runner_pid,
            "created_at": created_at,
            "mediation": mediation,
        }


class LeaseClock(BaseModel):
    """One observation of both wall and monotonic time."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    wall: int | float = Field(description="Observed wall-clock epoch seconds.")
    monotonic: int | float = Field(
        description="Observed monotonic seconds, preserving rollback detection."
    )


class GrantWindow(BaseModel):
    """Related observed times and the enclosing lease's maximum deadlines."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    clock: LeaseClock = Field(
        description="Issuance or renewal observation in both clock domains."
    )
    wall_deadline: int | float = Field(
        description="Enclosing lease's latest wall expiry."
    )
    monotonic_deadline: int | float = Field(
        description="Enclosing lease's latest monotonic expiry."
    )


class LeaseGrant(BaseModel):
    """One in-memory grant; GrantBook owns synchronization and secret indexing."""

    model_config = ConfigDict(
        strict=True, validate_assignment=True, extra="forbid", hide_input_in_errors=True
    )
    grant_id: str = Field(
        description="Safe random grant identity used in audit records."
    )
    lease_token: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Private parent lease binding, excluded from normal output.",
    )
    expires_at: int | float = Field(description="Current wall-clock expiry.")
    issued_monotonic: int | float = Field(
        description="Original monotonic issuance boundary."
    )
    expires_monotonic: int | float = Field(description="Current monotonic expiry.")
    revoked_at: int | float | None = Field(
        default=None, description="Observed revocation wall time, null until revoked."
    )

    @classmethod
    def from_window(
        cls, grant_id: str, lease_token: str, window: GrantWindow
    ) -> "LeaseGrant":
        """Construct both TTL deadlines without exceeding the enclosing lease."""
        return cls(
            grant_id=grant_id,
            lease_token=lease_token,
            expires_at=min(window.clock.wall + GRANT_TTL_SECONDS, window.wall_deadline),
            issued_monotonic=window.clock.monotonic,
            expires_monotonic=min(
                window.clock.monotonic + GRANT_TTL_SECONDS, window.monotonic_deadline
            ),
        )

    def bound_to(self, token: str) -> bool:
        """Compare only at the private parent-lease binding boundary."""
        return self.lease_token.get_secret_value() == token

    def renew(self, window: GrantWindow) -> None:
        """Update both expiry domains together after the book admits renewal."""
        self.expires_at = min(
            window.clock.wall + GRANT_TTL_SECONDS, window.wall_deadline
        )
        self.expires_monotonic = min(
            window.clock.monotonic + GRANT_TTL_SECONDS, window.monotonic_deadline
        )

    def revoke(self, wall_time: int | float) -> None:
        """Record the admitted revocation observation without changing grant identity."""
        self.revoked_at = wall_time

    def accepts(self, clock: LeaseClock) -> bool:
        """Preserve the existing expiry, monotonic rollback and revocation checks."""
        return (
            self.revoked_at is None
            and clock.wall < self.expires_at
            and self.issued_monotonic <= clock.monotonic < self.expires_monotonic
        )


class LeaseCleanupObservation(BaseModel):
    """Safe cleanup evidence, including malformed callback refusal."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    verified: bool = Field(
        description="Only an actual boolean callback verdict can confirm cleanup."
    )
    state: JsonValue = Field(
        description="Existing JSON diagnostic, or safe cleanup_error for an invalid callback result."
    )

    @classmethod
    def from_result(cls, verified, state) -> "LeaseCleanupObservation":
        """Keep malformed private callback values out of the result journal."""
        try:
            return cls(verified=verified, state=state)
        except ValidationError:
            return cls(verified=False, state="cleanup_error")


class LeaseRevocationRecord(BaseModel):
    """New denial/cleanup evidence, not a schema used to reject old lease files."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    reason: str = Field(description="Existing stable revocation reason.")
    revoked_grants: list[str] = Field(
        description="Safe identities of grants actually revoked."
    )
    detected_at: int | float = Field(
        description="Observed wall time of the revocation trigger."
    )
    revoked_at: int | float = Field(
        description="Observed wall time after authorization revocation."
    )
    cleanup_finished_at: int | float | None = Field(
        default=None, description="Observed cleanup wall time; omitted before cleanup."
    )
    detected_at_monotonic: int | float = Field(
        description="Observed monotonic trigger time."
    )
    revoked_at_monotonic: int | float = Field(
        description="Observed monotonic denial boundary."
    )
    cleanup_finished_at_monotonic: int | float | None = Field(
        default=None,
        description="Observed cleanup monotonic time; omitted before cleanup.",
    )
    cleanup_verified: bool | None = Field(
        default=None, description="Actual cleanup observation; omitted before cleanup."
    )
    state: JsonValue = Field(
        default=None,
        description="Existing safe cleanup diagnostic, omitted before cleanup.",
    )

    def to_record(self) -> dict:
        """Preserve both existing record variants without inventing cleanup evidence."""
        return self.model_dump(exclude_unset=True)


class LeaseRefusalRecord(BaseModel):
    """Observed refusal and cleanup outcome; neither success is inferred."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    reason: str = Field(description="Existing refused or lease_error state.")
    error_code: str = Field(description="Existing stable refusal code.")
    detected_at: int | float = Field(description="Observed wall time of refusal.")
    revoked_grants: list[str] = Field(description="Safe identities actually revoked.")
    revocation_verified: bool = Field(
        description="Whether authorization revocation was actually verified."
    )
    cleanup_verified: bool = Field(
        description="Whether exact owned-container cleanup was actually verified."
    )
    state: JsonValue = Field(description="Existing safe cleanup state diagnostic.")

    def to_record(self) -> dict:
        """Return the existing seven-field refusal evidence shape."""
        return self.model_dump()
