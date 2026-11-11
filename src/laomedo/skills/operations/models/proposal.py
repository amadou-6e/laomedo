"""Proposal contracts for authorized Skill operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator, model_validator
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from typing import Literal
import json
from laomedo.skills.registry.utils.paths import validate_relative_path
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
