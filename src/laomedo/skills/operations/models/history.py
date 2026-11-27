"""History contracts for authorized Skill operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue, field_serializer
from typing import Literal
from datetime import datetime, timezone
from uuid import uuid4
from laomedo.skills.registry.models import SkillImportRecord
from laomedo.skills.registry.models import SkillPolicyReference
from laomedo.skills.registry.models import SkillReference
from laomedo.skills.registry.utils.diff import patch_for
from laomedo.skills.operations.models.provenance import EditorProvenance
from laomedo.skills.operations.models.provenance import ImportedSkillEditor


class SkillCommit(BaseModel):
    """New commit hash preimage; the journal service computes and stores its ID."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    skill_id: str = Field(
        description="Skill whose append-only history receives this commit."
    )
    revision_id: str = Field(
        description="Immutable byte revision associated with this commit."
    )
    parent_commit: str | None = Field(
        description="Previous history identity; explicitly null for the initial import."
    )
    created_at: str = Field(
        description="Existing host UTC timestamp string, preserved verbatim."
    )
    message: str = Field(description="Explanation of the import or admitted edit.")
    files: list[str] = Field(
        description="Changed relative paths; imports list all added files (legacy roots may be empty)."
    )
    patch: str = Field(
        description="Exact existing unified patch bytes represented as text."
    )
    editor: EditorProvenance | ImportedSkillEditor = Field(
        description="Host provenance, independent of model-supplied content."
    )
    draft_id: str | None = Field(
        default=None,
        description="Originating edit draft; key omitted for initial import.",
    )
    policy_ref: SkillPolicyReference | None = Field(
        default=None,
        description="Admitted edit policy; key omitted for initial import.",
    )
    nonce: str = Field(
        description="Existing random history salt; unchanged format and generation."
    )

    @classmethod
    def from_import(cls, imported: SkillImportRecord, files: dict[str, bytes]):
        """Project the retained import event to a stable root commit, without edit authority."""
        return cls(
            skill_id=imported.skill_id,
            revision_id=imported.revision_id,
            parent_commit=None,
            created_at=imported.recorded_at,
            message=(
                "Initial import"
                if imported.origin == "import"
                else "Record existing import (original import time unknown)"
            ),
            files=sorted(files),
            patch=patch_for({}, files),
            editor=ImportedSkillEditor(),
            nonce=imported.nonce,
        )

    @classmethod
    def from_registered_revision(
        cls,
        reference: SkillReference,
        parent_commit: str,
        before: dict[str, bytes],
        after: dict[str, bytes],
    ):
        """Register retained canonical bytes without asserting missing edit provenance/time."""
        return cls(
            skill_id=reference.skill_id,
            revision_id=reference.revision_id,
            parent_commit=parent_commit,
            created_at=datetime.now(timezone.utc).isoformat(),
            message="Record existing promoted revision (original edit time unknown)",
            files=sorted(
                path
                for path in before.keys() | after.keys()
                if before.get(path) != after.get(path)
            ),
            patch=patch_for(before, after),
            editor=ImportedSkillEditor(),
            nonce=uuid4().hex,
        )

    def to_record(self) -> dict:
        """Preserve omission, provenance and ordering in the canonical hash preimage."""
        value = self.model_dump()
        value["editor"] = self.editor.model_dump(exclude_none=True)
        for key in ("draft_id", "policy_ref"):
            if key not in self.model_fields_set:
                del value[key]
        return value


class SkillCommitReceipt(BaseModel):
    """Computed journal identity paired with its newly written commit value."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    commit_id: str = Field(description="Canonical hash of the exact commit preimage.")
    record: SkillCommit = Field(
        description="New commit whose identity was computed by the journal service."
    )

    def to_payload(self) -> dict:
        """Flatten records at the public journal boundary."""
        return {"commit_id": self.commit_id, **self.record.to_record()}


class SkillOperationResult(BaseModel):
    """Existing public receipt after a proposal is frozen and journalled."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    status: Literal["proposed"] = Field(
        default="proposed", description="An edit has been proposed, not promoted."
    )
    promotion_performed: Literal[False] = Field(
        default=False, description="Skill operations do not update canonical latest."
    )
    commit: SkillCommitReceipt = Field(
        description="New typed commit and its computed history identity."
    )
    skill: SkillReference = Field(
        description="Existing three-field skill/revision/tree public binding."
    )

    @field_serializer("commit")
    def serialize_commit(self, value: SkillCommitReceipt) -> dict:
        """Preserve the flattened public receipt instead of exposing record nesting."""
        return value.to_payload()

    @field_serializer("skill")
    def serialize_skill(self, value: SkillReference) -> dict:
        """Project the skill identity binding."""
        return value.to_reference_payload()

    def to_payload(self) -> dict:
        """Serialize the receipt's public fields."""
        return self.model_dump()


class SkillFileChange(BaseModel):
    """A changed path in a historical-to-current file comparison."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    path: str = Field(description="Relative path in either immutable byte inventory.")
    status: Literal["added", "deleted", "modified"] = Field(
        description="Change relative to the selected historical revision."
    )
    before_hash: str | None = Field(
        description="Old file hash, explicitly null for additions."
    )
    after_hash: str | None = Field(
        description="Current file hash, explicitly null for deletions."
    )
    binary: bool = Field(description="Whether either existing side is non-text.")


class SkillComparison(BaseModel):
    """File changes and exact patch between a selected commit and current revision."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    skill_id: str = Field(description="Skill shared by both admitted revisions.")
    base_commit: dict[str, JsonValue] = Field(
        description="Retained historical commit metadata, preserving legacy extension fields."
    )
    base_revision: str = Field(
        description="Immutable byte revision selected from history."
    )
    current_revision: str = Field(description="Pinned byte revision currently viewed.")
    files: list[SkillFileChange] = Field(
        description="Sorted changed paths, with independently typed per-file metadata."
    )
    patch: str = Field(
        description="Exact unified patch including missing-final-newline evidence."
    )

    def to_payload(self) -> dict:
        """Project the public comparison; the service enforces response size."""
        return self.model_dump()
