"""New OAuth values with explicit private projections and excluded secrets."""

from urllib.parse import urlencode
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, field_validator


class OAuthAuthorizationRequest(BaseModel):
    """Related authorization parameters, before the existing browser handoff."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    client_id: str = Field(
        description="Existing dynamic or previously enrolled client identity."
    )
    ext_agent_host_id: str = Field(description="Existing app-owned host identity.")
    redirect_uri: str = Field(description="Previously admitted local callback URI.")
    scope: str = Field(description="Existing requested OAuth scope string.")
    resource: str = Field(description="Existing resource audience.")
    state: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Fresh anti-forgery state; private query sink only.",
    )
    nonce: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Fresh ID-token nonce; private query sink only.",
    )
    code_challenge: str = Field(
        description="Existing base64url SHA-256 PKCE challenge."
    )
    agent_name_hint: str | None = Field(
        default=None, description="Existing name hint only for new enrollment."
    )
    id_token_hint: SecretStr | JsonValue = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Existing account hint; legacy JSON values stay private without new reader admission.",
    )
    login_hint: JsonValue = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Legacy email claim hint, preserving existing provider JSON values.",
    )

    @field_validator("id_token_hint", mode="before")
    @classmethod
    def protect_token_hint(cls, value):
        """Protect ordinary token strings while retaining legacy query encoding."""
        return SecretStr(value) if isinstance(value, str) else value

    def to_query(self) -> str:
        """Unwrap only for the existing privileged OAuth authorization URL."""
        value = dict(
            client_id=self.client_id,
            ext_agent_host_id=self.ext_agent_host_id,
            response_type="code",
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            resource=self.resource,
            state=self.state.get_secret_value(),
            nonce=self.nonce.get_secret_value(),
            code_challenge_method="S256",
            code_challenge=self.code_challenge,
        )
        for key in ("agent_name_hint", "id_token_hint", "login_hint"):
            if key in self.model_fields_set:
                item = getattr(self, key)
                value[key] = (
                    item.get_secret_value() if isinstance(item, SecretStr) else item
                )
        return urlencode(value)


class OAuthAttempt(BaseModel):
    """New private sign-in attempt; the existing caller retains its lifecycle."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    url: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Credential-hint-bearing authorization URL for the browser only.",
    )
    state: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Anti-forgery state for callback comparison.",
    )
    nonce: SecretStr = Field(
        repr=False, exclude=True, description="Nonce for ID-token verification."
    )
    verifier: SecretStr = Field(
        repr=False, exclude=True, description="PKCE verifier for one token exchange."
    )
    redirect_uri: str = Field(description="Previously admitted local callback URI.")
    client_id: str | None = Field(
        description="Existing enrolled client or explicit null for dynamic enrollment."
    )
    previous_subject: JsonValue = Field(
        repr=False,
        exclude=True,
        description="Existing private subject observation, retained only by the attempt boundary.",
    )

    def to_private_payload(self) -> dict:
        """Preserve the existing seven-key private attempt boundary, never a log sink."""
        return dict(
            url=self.url.get_secret_value(),
            state=self.state.get_secret_value(),
            nonce=self.nonce.get_secret_value(),
            verifier=self.verifier.get_secret_value(),
            redirect_uri=self.redirect_uri,
            client_id=self.client_id,
            previous_subject=self.previous_subject,
        )


class OAuthCodeExchange(BaseModel):
    """One authorization-code exchange; no transport or retry policy lives here."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    client_id: str = Field(description="Previously admitted enrolled client identity.")
    code: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Single-use callback code, excluded from normal output.",
    )
    code_verifier: SecretStr = Field(
        repr=False, exclude=True, description="Original attempt's PKCE verifier."
    )
    redirect_uri: str = Field(description="Original attempt's admitted callback URI.")
    resource: str = Field(description="Existing OAuth resource audience.")

    def to_private_payload(self) -> dict:
        """Unwrap only for the existing HTTPS form encoder."""
        return dict(
            grant_type="authorization_code",
            client_id=self.client_id,
            code=self.code.get_secret_value(),
            code_verifier=self.code_verifier.get_secret_value(),
            redirect_uri=self.redirect_uri,
            resource=self.resource,
        )


class OAuthAccount(BaseModel):
    """New account write after existing subject, scope and token admission."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    client_id: str = Field(description="Admitted enrolled OAuth client.")
    subject: str = Field(
        repr=False,
        exclude=True,
        description="Verified account subject; private store only.",
    )
    issuer: str = Field(description="Verified ID-token issuer.")
    email: JsonValue = Field(
        repr=False,
        exclude=True,
        description="Legacy optional provider email claim, without stronger admission.",
    )
    ext_agent_host_id: str = Field(description="Existing app-owned host identity.")
    id_token: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Verified ID token; private account store only.",
    )
    access_token: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Admitted access credential; never ordinary dumps.",
    )
    refresh_token: SecretStr = Field(
        repr=False,
        exclude=True,
        description="Rotating credential; retained only by the host private store.",
    )
    scopes: list[str] = Field(
        description="Sorted granted scopes after existing required-scope checks."
    )
    expires_at: int | float = Field(
        description="Existing wall-clock expiry, preserving numeric representation."
    )
    generation: int | float = Field(
        description="Existing incremented generation, preserving legacy numeric representation."
    )
    state: str = Field(
        description="Initial account state, active after successful admission."
    )

    def to_private_record(self) -> dict:
        """Preserve the existing private account shape without exporting credentials elsewhere."""
        return dict(
            client_id=self.client_id,
            subject=self.subject,
            issuer=self.issuer,
            email=self.email,
            ext_agent_host_id=self.ext_agent_host_id,
            id_token=self.id_token.get_secret_value(),
            access_token=self.access_token.get_secret_value(),
            refresh_token=self.refresh_token.get_secret_value(),
            scopes=list(self.scopes),
            expires_at=self.expires_at,
            generation=self.generation,
            state=self.state,
        )
