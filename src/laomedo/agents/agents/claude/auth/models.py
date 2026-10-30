"""Access-only values with an explicitly privileged native JSON projection."""

from __future__ import annotations

import json
import math
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, SkipValidation
from pydantic import StrictFloat, StrictInt

from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError


class ClaudeAccessLoginRecord(BaseModel):
    """Retain selected parsed host-login values without serializing credentials.

    Optional observations are already parsed host JSON. They deliberately skip
    reinterpretation, coercion and new recursion limits at this compatibility
    boundary. Only ``to_private_bytes`` reveals values for the dedicated local
    helper's stdin; its result must never be logged or sent to an ordinary API.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", hide_input_in_errors=True
    )

    _OPTIONAL_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("scopes", "scopes"),
        ("subscription_type", "subscriptionType"),
        ("rate_limit_tier", "rateLimitTier"),
    )

    access_token: SecretStr = Field(
        validation_alias="accessToken",
        min_length=1,
        max_length=32768,
        repr=False,
        exclude=True,
        description="Access-only credential admitted from the selected host login.",
    )
    expires_at: StrictInt | Annotated[StrictFloat, Field(allow_inf_nan=False)] = Field(
        validation_alias="expiresAt",
        repr=False,
        exclude=True,
        description="Original finite expiry in milliseconds, preserving integer or float representation.",
    )
    scopes: SkipValidation[JsonValue] = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Opaque parsed native scopes observation, preserving absence and explicit null.",
    )
    subscription_type: SkipValidation[JsonValue] = Field(
        default=None,
        validation_alias="subscriptionType",
        repr=False,
        exclude=True,
        description="Opaque parsed native subscription observation without invented type restrictions.",
    )
    rate_limit_tier: SkipValidation[JsonValue] = Field(
        default=None,
        validation_alias="rateLimitTier",
        repr=False,
        exclude=True,
        description="Opaque parsed native rate-limit observation preserved only for the private helper.",
    )

    @classmethod
    def from_host_record(cls, value: JsonValue) -> ClaudeAccessLoginRecord:
        """Admit the parsed ``claudeAiOauth`` value using the original checks.

        The caller owns reading/parsing the host file. Never pass the whole file
        into Pydantic validation: it can contain a rotating refresh credential.
        """
        if not isinstance(value, dict):
            raise LocalClaudeLoginError("claude_host_login_unavailable")
        try:
            access = value["accessToken"]
            expires = value["expiresAt"]
            if (
                not isinstance(access, str)
                or not access
                or len(access) > 32768
                or type(expires) not in (int, float)
                or not math.isfinite(expires)
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise LocalClaudeLoginError("claude_host_login_unavailable") from None
        selected = {"accessToken": SecretStr(access), "expiresAt": expires}
        for _, wire_name in cls._OPTIONAL_KEYS:
            if wire_name in value:
                selected[wire_name] = value[wire_name]
        return cls(**selected)

    def require_expiry_after(self, required_expiry: float) -> None:
        """Refuse expiry at or before the caller's fixed admission threshold."""
        if self.expires_at <= required_expiry:
            raise LocalClaudeLoginError("claude_host_login_expired")

    def to_private_bytes(self) -> bytes:
        """Return the exact old writer's ordered/default JSON bytes for stdin."""
        login = {
            "accessToken": self.access_token.get_secret_value(),
            "expiresAt": self.expires_at,
        }
        for field_name, wire_name in self._OPTIONAL_KEYS:
            if field_name in self.model_fields_set:
                login[wire_name] = getattr(self, field_name)
        login["refreshToken"] = ""
        return json.dumps({"claudeAiOauth": login}).encode()
