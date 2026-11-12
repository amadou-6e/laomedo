"""Manual contracts for authorized Skill operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator
from typing import Literal
from laomedo.skills.operations.models.proposal import SkillProposal


class ManualSkillPermissions(BaseModel):
    """Host-only grants; neither authentication nor an edit policy grants publication."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    edit: bool = Field(
        default=False, description="Whether the host grants manual candidate creation."
    )
    publish: bool = Field(
        default=False, description="Whether the host grants registry promotion."
    )


class ManualSkillState(BaseModel):
    """Read-only editor bindings, without policies or backend capabilities."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    skill_id: str = Field(description="Registry identity of the selected skill.")
    selected_revision: str = Field(
        description="Immutable revision currently displayed by the editor."
    )
    head_revision: str = Field(description="Byte revision at the current history head.")
    head_commit: str = Field(description="Commit identity at the current history head.")
    latest_revision: str = Field(description="Currently published registry revision.")
    can_edit: bool = Field(
        description="Whether this selected revision admits manual editing."
    )
    can_publish: bool = Field(
        description="Whether this candidate admits registry promotion."
    )
    edit_enabled: bool = Field(
        description="Whether manual editing is configured by the host."
    )


class ManualSkillSave(BaseModel):
    """A durable browser request bound to exact history and one canonical proposal."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    request_id: str = Field(
        description="Canonical random UUID identifying one durable save request."
    )
    skill_id: str = Field(description="Registry identity of the selected skill.")
    revision_id: str = Field(description="Exact immutable candidate byte revision.")
    commit_id: str = Field(description="Exact retained commit identity.")
    operation: SkillProposal = Field(
        description="Validated atomic file changes for this save."
    )

    @field_validator("operation", mode="before")
    @classmethod
    def admit_proposal(cls, value):
        """Reuse the exact public proposal admission, including its error categories."""
        return SkillProposal.from_payload(value)

    @field_validator("request_id")
    @classmethod
    def canonical_request(cls, value):
        """Admit canonical random UUIDs, never arbitrary external replay keys."""
        from uuid import UUID

        parsed = UUID(value)
        if str(parsed) != value or parsed.version != 4:
            raise ValueError("skill_manual_invalid")
        return value

    def to_record(self):
        """Keep a canonical equality value without exposing service capabilities."""
        return {
            **self.model_dump(exclude={"operation"}),
            "operation": self.operation.to_payload(),
        }


class ManualSkillPublication(BaseModel):
    """Exact reviewed candidate and canonical base; no caller-supplied authority."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    skill_id: str = Field(description="Registry identity of the selected skill.")
    revision_id: str = Field(description="Exact immutable candidate byte revision.")
    commit_id: str = Field(description="Exact retained commit identity.")
    expected_latest: str = Field(
        description="Published revision used as the promotion compare-and-swap base."
    )


class ManualPublicationReceipt(BaseModel):
    """Durable confirmation of the exact registry promotion, independent of graph pins."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    skill_id: str = Field(description="Registry identity of the selected skill.")
    revision_id: str = Field(description="Exact immutable candidate byte revision.")
    commit_id: str = Field(description="Exact retained commit identity.")
    previous_revision: str = Field(
        description="Published revision replaced by the confirmed promotion."
    )
    confirmed_at: str = Field(
        description="Timestamp of durable registry promotion confirmation."
    )
    promotion_performed: Literal[True] = Field(
        default=True, description="True only when registry promotion is confirmed."
    )
