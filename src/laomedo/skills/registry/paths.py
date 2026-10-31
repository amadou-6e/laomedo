"""Validate registry names and portable relative paths."""

from __future__ import annotations

from pathlib import PurePosixPath
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.settings import NAME


def validate_name(value: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise SkillStoreError("invalid_skill_id")
    return value


def validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise SkillStoreError("unsafe_relative_path")
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or ":" in value
        or any(part in (".", "..") for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise SkillStoreError("unsafe_relative_path")
    return value
