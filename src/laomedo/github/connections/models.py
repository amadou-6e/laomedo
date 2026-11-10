"""Canonical masked OAuth protocol values; no permission follows from a token."""

import json
from math import isfinite
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class GitHubOAuthAttempt(BaseModel):
    """Keep pending state and verifier in broker memory, never graph payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    state: SecretStr = Field(
        exclude=True,
        repr=False,
        description="Unpredictable pending-request state.",
    )
    verifier: SecretStr = Field(
        exclude=True,
        repr=False,
        description="S256 proof held only by the broker.",
    )
    authorization_url: str = Field(
        exclude=True,
        repr=False,
        description="Explicit browser navigation URL containing pending state.",
    )


class GitHubConnectionCredential(BaseModel):
    """Host-only credential value with an explicit vault serialization boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    mode: Literal["browser", "token"] = Field(description="Deliberate connection mode.")
    access_token: SecretStr = Field(
        exclude=True,
        repr=False,
        min_length=1,
        max_length=4096,
        description="Host-only GitHub credential, never an ordinary model field.",
    )
    refresh_token: SecretStr | None = Field(
        default=None,
        exclude=True,
        repr=False,
        min_length=1,
        max_length=4096,
        description="Rotating browser credential; absent for a static supplied token.",
    )
    access_expires_at: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified access expiry in Unix seconds, or unknown for PATs.",
    )
    refresh_expires_at: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified refresh expiry in Unix seconds; never inferred for PATs.",
    )

    @model_validator(mode="after")
    def consistent_mode(self):
        """Refuse corrupt custody records rather than invent refresh capability."""
        for token in (self.access_token, self.refresh_token):
            if token is not None and any(
                not 33 <= ord(character) <= 126
                for character in token.get_secret_value()
            ):
                raise ValueError("github_credential_invalid")
        if self.mode == "browser":
            if (
                self.refresh_token is None
                or self.access_expires_at is None
                or self.refresh_expires_at is None
                or not 0 < self.access_expires_at <= self.refresh_expires_at
            ):
                raise ValueError("github_credential_invalid")
        else:
            value = self.access_token.get_secret_value()
            if (
                not value.startswith("github_pat_")
                or len(value) <= len("github_pat_")
                or any(
                    not (character.isalnum() or character == "_") for character in value
                )
                or self.refresh_token is not None
                or self.access_expires_at is not None
                or self.refresh_expires_at is not None
            ):
                raise ValueError("github_token_unsupported")
        return self

    @classmethod
    def from_oauth(cls, payload: dict, now: float):
        """Admit an expiring bearer pair without accepting provider error text."""
        access, refresh = payload.get("access_token"), payload.get("refresh_token")
        lifetime, refresh_lifetime = payload.get("expires_in"), payload.get(
            "refresh_token_expires_in"
        )
        if (
            not isfinite(now)
            or not isinstance(access, str)
            or not access
            or not isinstance(refresh, str)
            or not refresh
            or str(payload.get("token_type", "")).lower() != "bearer"
            or type(lifetime) is not int
            or not 0 < lifetime <= 315360000
            or type(refresh_lifetime) is not int
            or not lifetime <= refresh_lifetime <= 315360000
        ):
            raise ValueError("github_oauth_response_invalid")
        return cls(
            mode="browser",
            access_token=SecretStr(access),
            refresh_token=SecretStr(refresh),
            access_expires_at=now + lifetime,
            refresh_expires_at=now + refresh_lifetime,
        )

    @classmethod
    def from_token(cls, token: SecretStr):
        """Refuse classic/other token formats; online access verification is separate."""
        return cls(mode="token", access_token=token)

    def to_vault_value(self) -> SecretStr:
        """Project secrets only for the explicit host-vault write boundary."""
        payload = self.model_dump()
        payload["access_token"] = self.access_token.get_secret_value()
        payload["refresh_token"] = (
            self.refresh_token.get_secret_value() if self.refresh_token else None
        )
        return SecretStr(json.dumps(payload, separators=(",", ":")))

    @classmethod
    def from_vault_value(cls, value: SecretStr):
        """Reconstruct an explicitly authorized vault record without logging its text."""
        return cls.model_validate_json(value.get_secret_value())


class GitHubPrincipal(BaseModel):
    """Stable GitHub account identity verified with the selected credential."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    id: int = Field(strict=True, gt=0, description="Immutable numeric GitHub user ID.")
    login: str = Field(
        strict=True,
        min_length=1,
        max_length=100,
        description="Current GitHub account display login.",
    )


class GitHubConsentedRepository(BaseModel):
    """Repository identity admitted to explicit read consent, never write authority."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    id: int = Field(strict=True, gt=0, description="Immutable numeric repository ID.")
    full_name: str = Field(
        strict=True,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
        description="Verified current owner/name, without a URL.",
    )
    private: bool = Field(strict=True, description="Provider-reported visibility flag.")


class GitHubAppRecord(BaseModel):
    """Immutable non-secret app version; old connections retain their own version."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    id: UUID = Field(description="Broker-generated immutable app configuration ID.")
    owner_id: UUID = Field(description="Authenticated local profile owning this setup.")
    client_id: str = Field(
        strict=True, min_length=1, description="Configured app client ID."
    )
    slug: str = Field(
        strict=True,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="Configured GitHub App installation slug.",
    )
    secret_reference: UUID = Field(
        exclude=True,
        repr=False,
        description="Internal native-vault target, never public.",
    )


class GitHubConnectionRecord(BaseModel):
    """Non-secret current authority and its internal, separately held custody target."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    id: UUID = Field(description="Opaque broker-generated connection reference.")
    owner_id: UUID = Field(description="Upstream-verified local profile owner.")
    generation: int = Field(strict=True, ge=1, description="Monotonic admission fence.")
    mode: Literal["browser", "token"] = Field(description="Deliberate connection mode.")
    principal: GitHubPrincipal = Field(description="Verified stable GitHub account.")
    repositories: tuple[GitHubConsentedRepository, ...] = Field(
        description="Explicitly consented repository identities, not all visible repos."
    )
    state: Literal["ready", "reauthorization_required", "revoked"] = Field(
        description="Durable local admission state; not proof of remote revocation."
    )
    app_id: UUID | None = Field(
        default=None, description="Immutable app version used by browser refresh."
    )
    access_expires_at: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified access expiry, if known.",
    )
    refresh_expires_at: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Verified refresh expiry, if known.",
    )
    secret_reference: UUID = Field(
        exclude=True,
        repr=False,
        description="Internal native-vault target, never public.",
    )


class GitHubSecretReference(BaseModel):
    """Journaled custody responsibility containing no credential value."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(description="Exact broker-generated vault target UUID.")
    owner_id: UUID = Field(
        description="Authenticated local profile responsible for cleanup."
    )
    purpose: Literal["app", "connection"] = Field(description="Owning secret concern.")
    resource_id: UUID = Field(description="App configuration or connection UUID.")
