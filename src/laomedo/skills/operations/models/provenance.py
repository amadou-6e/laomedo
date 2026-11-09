"""Provenance contracts for authorized Skill operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import model_validator
from typing import Literal
from laomedo.skills.registry.errors import SkillStoreError


class EditorProvenance(BaseModel):
    """Host-supplied editing identity, distinct from proposed content."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    kind: Literal["operator", "agent"] = Field(
        description="Existing journal attribution vocabulary."
    )
    run_id: str | None = Field(
        default=None, description="Required run identity for an agent-authored edit."
    )
    thread_id: str | None = Field(
        default=None, description="Optional native conversation identity."
    )
    turn_id: str | None = Field(
        default=None, description="Optional native turn identity."
    )
    trace_ref: str | None = Field(
        default=None, description="Optional safe retained trace reference."
    )

    @model_validator(mode="after")
    def validate_provenance(self):
        """Check trusted editor provenance fields and preserve the established error categories."""
        if any(
            value is not None and len(value) > 512
            for value in (self.run_id, self.thread_id, self.turn_id, self.trace_ref)
        ):
            raise SkillStoreError("skill_editor_invalid")
        if self.kind == "agent" and not self.run_id:
            raise SkillStoreError("skill_agent_provenance_required")
        return self

    @classmethod
    def from_payload(cls, value):
        """Construct the canonical record from an admitted payload without changing its external shape."""
        value = {"kind": "operator"} if value is None else value
        if (
            not isinstance(value, dict)
            or value.get("kind") not in {"operator", "agent"}
            or set(value) - {"kind", "run_id", "thread_id", "turn_id", "trace_ref"}
            or any(not isinstance(v, str) or len(v) > 512 for v in value.values())
        ):
            raise SkillStoreError("skill_editor_invalid")
        if value["kind"] == "agent" and not value.get("run_id"):
            raise SkillStoreError("skill_agent_provenance_required")
        return cls(**value)

    def to_payload(self):
        """Project the record to its established wire shape without adding model-only fields."""
        return self.model_dump(exclude_none=True)


class ImportedSkillEditor(BaseModel):
    """Attribution of the initial immutable revision import."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    kind: Literal["import"] = Field(
        default="import",
        description="Import provenance; not an operator or agent edit.",
    )
