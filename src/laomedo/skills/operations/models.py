"""Validated internal skill edits and host-supplied provenance.

Only explicit projections cross HTTP/journal boundaries; their dictionaries implement
the public contract and stable error categories.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from binascii import Error as Base64Error

from laomedo.skills.registry.paths import validate_relative_path

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import JsonValue
from pydantic import field_serializer
from pydantic import field_validator
from pydantic import model_validator
from typing import Literal
from datetime import datetime, timezone
from uuid import uuid4
from laomedo.skills.registry.models import (
    SkillImportRecord,
    SkillPolicyReference,
    SkillReference,
)
from laomedo.skills.registry.diff import patch_for
import json
from laomedo.skills.registry.errors import SkillStoreError


class FileEdit(BaseModel):
    """One bounded replacement, deletion or immutable-base byte copy.

    Existing text/deletion projections remain unchanged. Binary encoding is a
    transport detail; only decoded bytes enter revision identity.
    """

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    path: str = Field(
        min_length=1,
        max_length=512,
        description="Admitted relative path in the editable skill bundle.",
    )
    content: str | None = Field(
        default=None, description="UTF-8 text, base64 bytes, or null for deletion."
    )
    encoding: Literal["utf-8", "base64"] = Field(
        default="utf-8",
        description="Wire representation of content; omitted text edits retain UTF-8.",
    )
    source_path: str | None = Field(
        default=None,
        description="Copy bytes from this file in the exact reserved base.",
    )

    @field_validator("path", "source_path")
    @classmethod
    def validate_path(cls, value):
        """Admit one portable edit path and retain the established path refusal category."""
        if value is None:
            return value
        if len(value) > 512:
            raise SkillStoreError("skill_operation_invalid")
        return validate_relative_path(value)

    @model_validator(mode="after")
    def validate_content(self):
        """Keep forms exclusive and validate bounded canonical binary before allocation."""
        if self.source_path is not None:
            if (
                "content" in self.model_fields_set
                or "encoding" in self.model_fields_set
            ):
                raise SkillStoreError("skill_operation_invalid")
        elif "content" not in self.model_fields_set:
            raise SkillStoreError("skill_operation_invalid")
        elif self.encoding == "base64":
            if self.content is None or len(self.content) > 4 * ((512 * 1024 + 2) // 3):
                raise SkillStoreError("skill_operation_invalid")
            try:
                decoded = b64decode(self.content, validate=True)
            except (ValueError, Base64Error):
                raise SkillStoreError("skill_operation_invalid") from None
            if (
                len(decoded) > 512 * 1024
                or b64encode(decoded).decode("ascii") != self.content
            ):
                raise SkillStoreError("skill_operation_invalid")
        elif self.content is not None and len(self.content.encode()) > 512 * 1024:
            raise SkillStoreError("skill_operation_invalid")
        return self

    @classmethod
    def from_payload(cls, value):
        """Admit the three exact wire forms without coercion or parser disclosures."""
        if not isinstance(value, dict) or not (
            set(value) == {"path", "content"}
            or set(value) == {"path", "source_path"}
            or set(value) == {"path", "content", "encoding"}
            and value["encoding"] == "base64"
        ):
            raise SkillStoreError("skill_operation_invalid")
        validate_relative_path(value["path"])
        if "source_path" in value:
            validate_relative_path(value["source_path"])
        try:
            return cls(**value)
        except (ValueError, TypeError):
            raise SkillStoreError("skill_operation_invalid") from None

    def to_payload(self):
        """Preserve legacy request equality; emit new fields only for the new forms."""
        if self.source_path is not None:
            return {"path": self.path, "source_path": self.source_path}
        result = {"path": self.path, "content": self.content}
        if self.encoding == "base64":
            result["encoding"] = self.encoding
        return result

    def to_bytes(self, base: dict[str, bytes]) -> bytes | None:
        """Resolve only against immutable before-bytes, independent of batch ordering."""
        if self.source_path is not None:
            if self.source_path not in base:
                raise SkillStoreError("skill_file_missing")
            return base[self.source_path]
        if self.content is None:
            return None
        return (
            b64decode(self.content)
            if self.encoding == "base64"
            else self.content.encode()
        )


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
        """Reject duplicate and case-alias paths before an edit proposal can be applied."""
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
        edits = tuple(FileEdit.from_payload(edit) for edit in value["files"])
        for edit in edits:
            path = edit.path
            if path.casefold() in seen:
                raise SkillStoreError("skill_operation_invalid")
            seen.add(path.casefold())
        return cls(
            action=value["action"],
            message=value["message"],
            files=edits,
        )

    def to_payload(self):
        """Project the record to its established wire shape without adding model-only fields."""
        return {
            "action": self.action,
            "message": self.message,
            "files": [edit.to_payload() for edit in self.files],
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
