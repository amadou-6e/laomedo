"""Canonical masked OAuth protocol values; no permission follows from a token."""

import json
from collections.abc import Awaitable, Callable
from math import isfinite
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from laomedo.github.connections.settings import GITHUB_REPOSITORY_LIMIT
from laomedo.skills.sources.models import PendingSkillImport


class GitHubOAuthAttempt(BaseModel):
    """Keep pending state and verifier in broker memory, never graph payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    state: SecretStr = Field(
        exclude=True,
        repr=False,
        min_length=32,
        max_length=128,
        description="Unpredictable pending-request state.",
    )
    verifier: SecretStr = Field(
        exclude=True,
        repr=False,
        min_length=43,
        max_length=128,
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


class GitHubRepositoryIdentity(BaseModel):
    """Verified repository identity; a candidate is not explicit consent or authority."""

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
    repositories: tuple[GitHubRepositoryIdentity, ...] = Field(
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

    @model_validator(mode="after")
    def consistent_authority(self):
        """Refuse corrupt modes and duplicate consent instead of widening admission."""
        if len(self.repositories) > GITHUB_REPOSITORY_LIMIT or len(
            {repo.id for repo in self.repositories}
        ) != len(self.repositories):
            raise ValueError("github_connection_invalid")
        if self.mode == "browser":
            if (
                self.app_id is None
                or self.access_expires_at is None
                or self.refresh_expires_at is None
                or not 0 < self.access_expires_at <= self.refresh_expires_at
            ):
                raise ValueError("github_connection_invalid")
        elif self.app_id is not None or self.refresh_expires_at is not None:
            raise ValueError("github_connection_invalid")
        return self


class GitHubSecretReference(BaseModel):
    """Journaled custody responsibility containing no credential value."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(description="Exact broker-generated vault target UUID.")
    owner_id: UUID = Field(
        description="Authenticated local profile responsible for cleanup."
    )
    purpose: Literal["app", "connection"] = Field(description="Owning secret concern.")
    resource_id: UUID = Field(description="App configuration or connection UUID.")


class GitHubRepositoryInventory(BaseModel):
    """Verified account and complete bounded candidate list, before read consent."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    principal: GitHubPrincipal = Field(
        description="Account verified by this credential."
    )
    repositories: tuple[GitHubRepositoryIdentity, ...] = Field(
        description="Complete bounded visible repository candidates, not read consent."
    )
    elapsed_seconds: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Measured online verification time in seconds.",
    )


class GitHubConnectionScope(BaseModel):
    """Trusted request-local admission projection, never a browser input schema."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    owner_id: UUID = Field(description="Upstream-verified ordinary local profile UUID.")
    lease_binding: SecretStr = Field(
        exclude=True,
        repr=False,
        description="Digest binding to this explicit-login browser lease.",
    )
    check: Callable[[], Awaitable[None]] = Field(
        exclude=True,
        repr=False,
        description="Host-bound current upstream/lease revalidation.",
    )

    async def revalidate(self):
        """Delegate authentication proof to the trusted adapter, never browser data."""
        await self.check()


class GitHubConnectionAttempt(BaseModel):
    """One finite pending attempt; failed or stale attempts never replace ready state."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    id: UUID = Field(description="Broker-generated pending request identity.")
    owner_id: UUID = Field(description="Verified initiating local profile.")
    lease_binding: SecretStr = Field(
        exclude=True,
        repr=False,
        description="Exact initiating explicit-login lease digest.",
    )
    connection_id: UUID = Field(
        description="Connection to create or deliberately reconnect."
    )
    expected_generation: int = Field(
        strict=True,
        ge=0,
        description="Selected generation CAS; zero means a new connection.",
    )
    expected_principal_id: int | None = Field(
        default=None,
        strict=True,
        gt=0,
        description="Existing account identity required on reconnect.",
    )
    mode: Literal["browser", "token"] = Field(
        description="Deliberately chosen connection mode."
    )
    app_id: UUID | None = Field(
        default=None, description="Immutable browser-app setup version."
    )
    expires_at: float = Field(
        allow_inf_nan=False,
        gt=0,
        description="Absolute pending-request expiry in Unix seconds.",
    )
    oauth: GitHubOAuthAttempt | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="One-use protocol state before callback consumption.",
    )
    inventory: GitHubRepositoryInventory | None = Field(
        default=None, description="Verified candidates awaiting explicit consent."
    )
    secret_reference: UUID | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Provisional native-vault target, if verification finished.",
    )

    def public(self):
        """Return safe UI state with explicit authorization navigation only when pending."""
        return {
            "request_id": str(self.id),
            "connection_id": str(self.connection_id),
            "expires_at": self.expires_at,
            "phase": "authorize" if self.oauth is not None else "consent",
            "authorization_url": (
                self.oauth.authorization_url if self.oauth is not None else None
            ),
            "inventory": (
                self.inventory.model_dump(mode="json") if self.inventory else None
            ),
        }


class GitHubReadAuthorization(BaseModel):
    """Exact current consent/provenance binding for one private user read."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    owner_id: UUID = Field(description="Authenticated local profile owning the read.")
    connection_id: UUID = Field(
        description="Explicit selected connection, never inferred from a hash."
    )
    generation: int = Field(
        strict=True, ge=1, description="Current admission generation before this read."
    )
    repository: GitHubRepositoryIdentity = Field(
        description="Exact consented numeric repository identity."
    )
    principal: GitHubPrincipal = Field(
        description="Account verified online for this user read."
    )
    deadline: float = Field(
        allow_inf_nan=False,
        description="Monotonic total-read deadline, including release.",
    )
    consumed_bytes: int = Field(
        default=0,
        strict=True,
        ge=0,
        description="API response bytes already consumed by this user read.",
    )


class GitHubReadPage(BaseModel):
    """Internal bounded provider JSON with a non-followed pagination signal."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    payload: dict | list = Field(
        exclude=True,
        repr=False,
        description="Bounded raw provider JSON, never public serialization.",
    )
    next_page: bool = Field(
        description="Provider advertised another page; never its target URL."
    )


class GitHubSkillRevision(BaseModel):
    """One exact ref snapshot and validated candidate, before private registry import."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    label: str = Field(description="Exact heads/tags label and commit snapshot.")
    commit: str = Field(
        pattern=r"^[0-9a-f]{40}$", description="Exact resolved Git commit identity."
    )
    candidate: PendingSkillImport = Field(
        description="Canonical validated Skill bytes and private origin."
    )


class GitHubConnectionStatus(BaseModel):
    """Safe custody availability projection, distinct from fresh online permission."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    connection: GitHubConnectionRecord = Field(
        description="Persisted non-secret connection identity and consent."
    )
    availability: Literal[
        "ready", "expired", "reauthorization_required", "revoked", "unavailable"
    ] = Field(
        description="Current local custody/lifetime availability, not online permission."
    )
    credential_cleanup_pending: bool = Field(
        default=False,
        description="An inactive local credential still needs confirmed removal.",
    )


class GitHubResponseBinding(BaseModel):
    """Exactly one trusted resource snapshot for private response release."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    owner_id: UUID = Field(
        description="Verified local profile receiving this response."
    )
    revision: int | None = Field(
        default=None,
        strict=True,
        ge=0,
        description="Owner metadata revision captured under the commit lock.",
    )
    connection: GitHubConnectionRecord | None = Field(
        default=None, description="Exact connection result generation and state."
    )
    request_id: UUID | None = Field(
        default=None, description="Still-live owner/lease-bound pending request."
    )
    authorization: GitHubReadAuthorization | None = Field(
        default=None, description="Exact repository/read generation and deadline."
    )

    @model_validator(mode="after")
    def one_resource(self):
        """Refuse ambiguous or mismatched authority snapshots rather than widening one."""
        if (
            sum(
                value is not None
                for value in (
                    self.revision,
                    self.connection,
                    self.request_id,
                    self.authorization,
                )
            )
            != 1
        ):
            raise ValueError("github_response_binding_invalid")
        if self.connection is not None and self.connection.owner_id != self.owner_id:
            raise ValueError("github_response_binding_invalid")
        if (
            self.authorization is not None
            and self.authorization.owner_id != self.owner_id
        ):
            raise ValueError("github_response_binding_invalid")
        return self
