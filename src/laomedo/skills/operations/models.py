"""Validated internal skill edits and host-supplied provenance.

Only explicit projections cross HTTP/journal boundaries; their dictionaries retain
the existing public contract and stable error categories.
"""

from __future__ import annotations

from laomedo.skills.registry.paths import validate_relative_path

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import JsonValue
from pydantic import field_serializer
from pydantic import field_validator
from pydantic import model_validator
from typing import Literal
from laomedo.skills.registry.models import SkillPolicyReference, SkillReference
import json
from laomedo.skills.registry.errors import SkillStoreError


class FileEdit(BaseModel):
    """One admitted relative file replacement or deletion."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    path: str = Field(
        min_length=1,
        max_length=512,
        description="Admitted relative path in the editable skill bundle.",
    )
    content: str | None = Field(
        description="UTF-8 replacement text; null requests deletion."
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value):
        return validate_relative_path(value)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value):
        if value is not None and len(value.encode()) > 512 * 1024:
            raise SkillStoreError("skill_operation_invalid")
        return value


class SkillProposal(BaseModel):
    """Internal strict record; use from_payload at the public decoding boundary.

    from_payload repeats the wire checks before construction to preserve stable
    SkillStoreError categories. Direct internal construction uses ValidationError;
    validator exceptions must never be forwarded as public error messages.
    """

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    action: Literal["modify"] = Field(
        description="Only atomic multi-file modification is admitted."
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="Human-readable explanation retained with the commit.",
    )
    files: tuple[FileEdit, ...] = Field(
        min_length=1,
        max_length=128,
        description="Unique admitted file replacements and deletions.",
    )

    @model_validator(mode="after")
    def validate_unique_paths(self):
        if len({edit.path.casefold() for edit in self.files}) != len(self.files):
            raise SkillStoreError("skill_operation_invalid")
        return self

    @classmethod
    def from_payload(cls, value):
        """Only content and explanation can be supplied by a model."""
        value = getattr(value, "data", getattr(value, "text", value))
        if isinstance(value, dict) and set(value) == {"text"}:
            value = value["text"]
        if isinstance(value, str):
            if len(value.encode()) > 4 * 1024 * 1024:
                raise SkillStoreError("skill_operation_invalid")
            try:
                value = json.loads(value)
            except ValueError:
                raise SkillStoreError("skill_operation_invalid") from None
        if (
            not isinstance(value, dict)
            or set(value) != {"action", "message", "files"}
            or value["action"] != "modify"
            or not isinstance(value["message"], str)
            or not 1 <= len(value["message"]) <= 2000
            or not isinstance(value["files"], list)
            or not 1 <= len(value["files"]) <= 128
        ):
            raise SkillStoreError("skill_operation_invalid")
        seen = set()
        for edit in value["files"]:
            if not isinstance(edit, dict) or set(edit) != {"path", "content"}:
                raise SkillStoreError("skill_operation_invalid")
            path = validate_relative_path(edit["path"])
            if (
                path.casefold() in seen
                or len(path) > 512
                or edit["content"] is not None
                and (
                    not isinstance(edit["content"], str)
                    or len(edit["content"].encode()) > 512 * 1024
                )
            ):
                raise SkillStoreError("skill_operation_invalid")
            seen.add(path.casefold())
        return cls(
            action=value["action"],
            message=value["message"],
            files=tuple(FileEdit(**edit) for edit in value["files"]),
        )

    def to_payload(self):
        return {
            "action": self.action,
            "message": self.message,
            "files": [edit.model_dump() for edit in self.files],
        }


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
        description="Changed relative paths; empty for the initial import."
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
        """Flatten only at the existing public journal boundary."""
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
        """Preserve the existing skill binding projection."""
        return value.to_reference_payload()

    def to_payload(self) -> dict:
        """Serialize the existing receipt without adding or omitting fields."""
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
        """Return the existing public comparison; the service enforces response size."""
        return self.model_dump()
