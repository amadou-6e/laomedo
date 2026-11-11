"""Stored private provenance and request-local buffered read results."""

from uuid import UUID
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from laomedo.github.connections.models import GitHubReadAuthorization
from laomedo.skills.sources.models import SkillSourceChoice


class PrivateSkillOrigin(BaseModel):
    """Exact byte provenance, never continuing read or execution authority."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    owner_id: UUID = Field(description="Authenticated profile owning the stored bytes.")
    connection_id: UUID = Field(
        description="Explicit connection that supplied the bytes."
    )
    repository_id: int = Field(
        strict=True, gt=0, description="Consented numeric repository identity."
    )
    choice: SkillSourceChoice = Field(
        description="Canonical discovered Skill name and folder."
    )
    skill_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
        description="Namespace-local Skill identity.",
    )
    revision_id: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$", description="Canonical immutable bundle hash."
    )
    commit: str = Field(pattern=r"^[0-9a-f]{40}$", description="Exact source commit.")
    label: str = Field(description="Discovered heads/tags label at import time.")


class PrivateSkillResult(BaseModel):
    """Buffered JSON plus the exact authorization required before body release."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    authorization: GitHubReadAuthorization = Field(
        description="Fresh request-local online admission."
    )
    payload: dict[str, Any] = Field(
        description="Fully buffered JSON response, never an iterator."
    )


class PrivateSkillRequest(BaseModel):
    """Explicit browser connection/repository selection; owner comes from its session."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    connection_id: UUID = Field(description="Selected opaque connection reference.")
    repository_id: int = Field(
        strict=True, gt=0, description="Selected consented repository ID."
    )


class PrivateSkillChoiceRequest(PrivateSkillRequest):
    """Select one canonical choice, independently rediscovered before import."""

    choice: str = Field(
        strict=True,
        min_length=1,
        max_length=2048,
        description="Exact discovered choice identity.",
    )


class PrivateSkillHistoryRequest(PrivateSkillRequest):
    """Select a namespace-local Skill without implying authority from its identity."""

    skill_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
        description="Selected private Skill identity.",
    )


class PrivateSkillRevisionRequest(PrivateSkillHistoryRequest):
    """Select exact retained bytes for an authenticated inspection."""

    revision_id: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Exact immutable retained revision.",
    )


class PrivateSkillCompareRequest(PrivateSkillHistoryRequest):
    """Select two retained revisions of the same authorized private Skill."""

    before: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$", description="Exact comparison base revision."
    )
    after: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Exact comparison target revision.",
    )
