"""Validated internal skill edits and host-supplied provenance.

Only explicit projections cross HTTP/journal boundaries; their dictionaries retain
the existing public contract and stable error categories.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator
from typing import Literal
import json
import laomedo.skills.registry.errors as _registry_errors
import laomedo.skills.registry.utils as _registry_utils


class FileEdit(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    path: str = Field(min_length=1, max_length=512)
    content: str | None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value):
        return _registry_utils._safe_relative(value)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value):
        if value is not None and len(value.encode()) > 512 * 1024:
            raise _registry_errors.SkillStoreError("skill_operation_invalid")
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
    action: Literal["modify"]
    message: str = Field(min_length=1, max_length=2000)
    files: tuple[FileEdit, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_unique_paths(self):
        if len({edit.path.casefold() for edit in self.files}) != len(self.files):
            raise _registry_errors.SkillStoreError("skill_operation_invalid")
        return self

    @classmethod
    def from_payload(cls, value):
        """Only content and explanation can be supplied by a model."""
        value = getattr(value, "data", getattr(value, "text", value))
        if isinstance(value, dict) and set(value) == {"text"}:
            value = value["text"]
        if isinstance(value, str):
            if len(value.encode()) > 4 * 1024 * 1024:
                raise _registry_errors.SkillStoreError("skill_operation_invalid")
            try:
                value = json.loads(value)
            except ValueError:
                raise _registry_errors.SkillStoreError(
                    "skill_operation_invalid"
                ) from None
        if (
            not isinstance(value, dict)
            or set(value) != {"action", "message", "files"}
            or value["action"] != "modify"
            or not isinstance(value["message"], str)
            or not 1 <= len(value["message"]) <= 2000
            or not isinstance(value["files"], list)
            or not 1 <= len(value["files"]) <= 128
        ):
            raise _registry_errors.SkillStoreError("skill_operation_invalid")
        seen = set()
        for edit in value["files"]:
            if not isinstance(edit, dict) or set(edit) != {"path", "content"}:
                raise _registry_errors.SkillStoreError("skill_operation_invalid")
            path = _registry_utils._safe_relative(edit["path"])
            if (
                path.casefold() in seen
                or len(path) > 512
                or edit["content"] is not None
                and (
                    not isinstance(edit["content"], str)
                    or len(edit["content"].encode()) > 512 * 1024
                )
            ):
                raise _registry_errors.SkillStoreError("skill_operation_invalid")
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
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    kind: Literal["operator", "agent"]
    run_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    trace_ref: str | None = None

    @model_validator(mode="after")
    def validate_provenance(self):
        if any(
            value is not None and len(value) > 512
            for value in (self.run_id, self.thread_id, self.turn_id, self.trace_ref)
        ):
            raise _registry_errors.SkillStoreError("skill_editor_invalid")
        if self.kind == "agent" and not self.run_id:
            raise _registry_errors.SkillStoreError("skill_agent_provenance_required")
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
            raise _registry_errors.SkillStoreError("skill_editor_invalid")
        if value["kind"] == "agent" and not value.get("run_id"):
            raise _registry_errors.SkillStoreError("skill_agent_provenance_required")
        return cls(**value)

    def to_payload(self):
        return self.model_dump(exclude_none=True)
