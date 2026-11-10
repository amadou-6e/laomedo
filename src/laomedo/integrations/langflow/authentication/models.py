"""Private lease records; browser cookies never enter serialized models."""

from uuid import UUID

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
