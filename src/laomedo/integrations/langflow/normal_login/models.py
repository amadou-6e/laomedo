"""Non-secret ownership metadata for the isolated local app."""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class RuntimeMarker(BaseModel):
    """Explicit bootstrap identity; no password or credential representation."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    purpose: Literal["laomedo-normal-login"] = Field(
        description="Runtime ownership tag."
    )
    version: Literal[1] = Field(description="Marker schema version.")
    port: int = Field(ge=1024, le=65535, description="Fixed loopback origin port.")
    bootstrap_admin: str | None = Field(
        default=None, description="Explicitly bootstrapped administrator name."
    )
    database: Path | None = Field(
        default=None, description="Verified bootstrap database path."
    )
