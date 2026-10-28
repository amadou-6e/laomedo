"""Validate and package skill source bundles."""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import json
import laomedo.skills.inspection.constants as _inspection_constants
import laomedo.skills.registry.constants as _registry_constants
import laomedo.skills.registry.errors as _registry_errors
import laomedo.skills.registry.utils as _registry_utils
import laomedo.skills.sources.constants as _sources_constants
import laomedo.skills.sources.errors as _sources_errors
import os
import re
import urllib.error


def _excluded(parts):
    return any(
        p in _sources_constants.SKIP or p.startswith(".") or p.endswith(".local")
        for p in parts
    )


def _name(data, fallback):
    text = data.decode("utf-8").replace("\r\n", "\n")
    frontmatter = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.S)
    header = frontmatter.group(1) if frontmatter else ""
    match = re.search(r"^name:[ \t]*(.*?)[ \t]*$", header, re.M)
    value = match.group(1) if match else fallback
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if not _registry_constants.NAME.fullmatch(value):
        raise _sources_errors.SourceError("skill_name_invalid")
    return value


def _bundle(files):
    if (
        not files
        or "SKILL.md" not in files
        or len(files) > _inspection_constants.MAX_FILES
    ):
        raise _sources_errors.SourceError("source_bundle_invalid")
    if sum(map(len, files.values())) > _inspection_constants.MAX_BUNDLE_BYTES:
        raise _sources_errors.SourceError("source_limit_exceeded")
    paths = set()
    for path, content in files.items():
        _bundle_path(path)
        normalized = path.casefold()
        if normalized in paths or any(
            normalized.startswith(p + "/") or p.startswith(normalized + "/")
            for p in paths
        ):
            raise _sources_errors.SourceError("source_bundle_unsafe")
        paths.add(normalized)
        parts = PurePosixPath(path).parts
        if (
            not parts
            or path.startswith("/")
            or ".." in parts
            or any(
                p.lower() in _sources_constants.SECRET or p.lower().startswith(".env")
                for p in parts
            )
            or len(parts) > 17
            or len(content) > _inspection_constants.MAX_FILE_BYTES
        ):
            raise _sources_errors.SourceError("source_bundle_unsafe")
    return files


def _bundle_path(path):
    try:
        _registry_utils._safe_relative(path)
    except _registry_errors.SkillStoreError:
        raise _sources_errors.SourceError("source_bundle_unsafe") from None
    if any(
        p.lower() in _sources_constants.SECRET or p.lower().startswith(".env")
        for p in PurePosixPath(path).parts
    ):
        raise _sources_errors.SourceError("source_bundle_unsafe")
    for part in PurePosixPath(path).parts:
        if (
            part.endswith((".", " "))
            or re.search(r'[<>"|?*]', part)
            or re.fullmatch(
                r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", part.split(".")[0]
            )
        ):
            raise _sources_errors.SourceError("source_bundle_unsafe")
