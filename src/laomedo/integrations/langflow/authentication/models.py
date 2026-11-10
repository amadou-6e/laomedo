"""Private lease records; browser cookies never enter serialized models."""

from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class PrivateSession(BaseModel):
    """The owner and absolute lifetime established by an upstream login."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: UUID
    issued_at: float = Field(strict=True, ge=0, allow_inf_nan=False)
    expires_at: float = Field(strict=True, gt=0, allow_inf_nan=False)


class IssuedPrivateSession(BaseModel):
    """An in-process cookie handoff; serialization exposes only safe metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session: PrivateSession
    cookie: SecretStr = Field(exclude=True, repr=False)


class PrivateBrowserContext(BaseModel):
    """A request-local authorization projection, never a browser owner assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    session: PrivateSession
    cookie: SecretStr = Field(exclude=True, repr=False)
    upstream_token: SecretStr = Field(exclude=True, repr=False)


class PrivateRuntimeMarker(BaseModel):
    """Ownership and fixed-origin admission for one private connection installation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    purpose: Literal["laomedo-private-github"] = "laomedo-private-github"
    version: Literal[1] = 1
    origin: str
