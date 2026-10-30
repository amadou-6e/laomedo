"""Admit source bundle paths and byte limits before registry writes."""

from __future__ import annotations
from pathlib import PurePosixPath
import re
from laomedo.skills.inspection.settings import (
    MAX_FILES,
    MAX_FILE_BYTES,
    MAX_BUNDLE_BYTES,
)
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.paths import validate_relative_path
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.settings import SECRET


def validate_bundle(files):
    if not files or "SKILL.md" not in files or len(files) > MAX_FILES:
        raise SourceError("source_bundle_invalid")
    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise SourceError("source_limit_exceeded")
    paths = set()
    for path, content in files.items():
        validate_bundle_path(path)
        normalized = path.casefold()
        if normalized in paths or any(
            (
                normalized.startswith(p + "/") or p.startswith(normalized + "/")
                for p in paths
            )
        ):
            raise SourceError("source_bundle_unsafe")
        paths.add(normalized)
        parts = PurePosixPath(path).parts
        if (
            not parts
            or path.startswith("/")
            or ".." in parts
            or any((p.lower() in SECRET or p.lower().startswith(".env") for p in parts))
            or (len(parts) > 17)
            or (len(content) > MAX_FILE_BYTES)
        ):
            raise SourceError("source_bundle_unsafe")
    return files


def validate_bundle_path(path):
    try:
        validate_relative_path(path)
    except SkillStoreError:
        raise SourceError("source_bundle_unsafe") from None
    if any(
        (
            p.lower() in SECRET or p.lower().startswith(".env")
            for p in PurePosixPath(path).parts
        )
    ):
        raise SourceError("source_bundle_unsafe")
    for part in PurePosixPath(path).parts:
        if (
            part.endswith((".", " "))
            or re.search('[<>"|?*]', part)
            or re.fullmatch(
                "(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", part.split(".")[0]
            )
        ):
            raise SourceError("source_bundle_unsafe")
