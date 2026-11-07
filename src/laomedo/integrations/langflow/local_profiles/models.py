"""Safe local profile boundary models, independent of upstream user payloads."""

from hmac import compare_digest
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from laomedo.integrations.langflow.local_profiles.settings import (
    MAX_PROFILE_NAME_LENGTH,
    PIN_DIGITS,
    SYSTEM_PROFILE_NAME,
)


class ProfileCreateRequest(BaseModel):
    """Validated registration input; credential values never belong to output."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: str = Field(strict=True, max_length=MAX_PROFILE_NAME_LENGTH)
    pin: SecretStr = Field(exclude=True, repr=False)
    confirmation: SecretStr = Field(exclude=True, repr=False)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("profile_name_invalid")
        name = value.strip()
        if not name or name.casefold() == SYSTEM_PROFILE_NAME.casefold():
            raise ValueError("profile_name_invalid")
        if any(ord(character) < 32 or ord(character) == 127 for character in name):
            raise ValueError("profile_name_invalid")
        return name

    @field_validator("pin", "confirmation")
    @classmethod
    def validate_pin(cls, value: SecretStr) -> SecretStr:
        pin = value.get_secret_value()
        if len(pin) != PIN_DIGITS or not pin.isascii() or not pin.isdecimal():
            raise ValueError("profile_pin_invalid")
        return value

    @model_validator(mode="after")
    def confirm_pin(self) -> "ProfileCreateRequest":
        if not compare_digest(
            self.pin.get_secret_value(), self.confirmation.get_secret_value()
        ):
            raise ValueError("profile_pin_mismatch")
        return self


class ProfileSummary(BaseModel):
    """Only safe picker identity, never hashes, roles, keys or system records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str


class ProfileIndex(BaseModel):
    """An empty picker is a normal first-run state, not an auth failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profiles: tuple[ProfileSummary, ...] = ()
    pin_digits: Literal[6] = PIN_DIGITS


class ProfileRuntimeMarker(BaseModel):
    """Explicit ownership of a fresh, isolated loopback profile installation."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    purpose: Literal["laomedo-local-profiles"]
    version: Literal[1]
    port: int = Field(ge=1024, le=65535)
