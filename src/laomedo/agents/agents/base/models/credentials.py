"""Credentials values owned by the shared Agent capability."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr


class CredentialBinding(BaseModel):
    """Public authentication identity/outcome metadata, never login material."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    credential_mode: str = Field(
        description="Authentication mode selected by trusted host startup."
    )
    credential_ref: str | None = Field(
        description="Safe connection identity, never login material."
    )
    auth_outcome: str = Field(description="Observed authentication admission outcome.")


class CredentialRequest(BaseModel):
    """Provider-local credential admission constraints, with no secret material."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    minimum_validity_seconds: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Required remaining validity when native policy can establish it.",
    )
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Absolute monotonic deadline for credential preparation.",
    )

    timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        allow_inf_nan=False,
        description="Native credential-check timeout ceiling, separately clamped to the request deadline.",
    )


class CredentialMaterial(BaseModel):
    """Private host transfer of one credential and its existing public identity."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    token: SecretStr | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Borrowed native credential; only explicit host projection may unwrap it.",
    )
    identity: dict[str, JsonValue] | None = Field(
        default=None,
        repr=False,
        description="Existing nonsecret connection metadata, never raw login state.",
    )
    binding: CredentialBinding = Field(
        description="Public preparation/identity outcome with no credential material."
    )

    def native_pair(self):
        """Unwrap only at the existing host launch boundary, preserving native identity."""
        return (
            self.token.get_secret_value() if self.token is not None else None
        ), self.identity


class CredentialAdmission(BaseModel):
    """Public native binding and optional excluded host launch material."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    binding: CredentialBinding = Field(
        description="Admitted public credential metadata."
    )
    material: CredentialMaterial | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Explicit host-only native launch material; no universal token requirement.",
    )
