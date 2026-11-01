"""Source-specific exclusion and frontmatter naming rules."""

from __future__ import annotations
import re
from laomedo.skills.registry.settings import NAME
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.settings import SKIP


def excluded_parts(parts):
    return any((p in SKIP or p.startswith(".") or p.endswith(".local") for p in parts))


def skill_name(data, fallback):
    text = data.decode("utf-8").replace("\r\n", "\n")
    frontmatter = re.match(
        "\\A---[ \\t]*\\r?\\n(.*?)\\r?\\n---(?:\\r?\\n|\\Z)", text, re.S
    )
    header = frontmatter.group(1) if frontmatter else ""
    match = re.search("^name:[ \\t]*(.*?)[ \\t]*$", header, re.M)
    value = match.group(1) if match else fallback
    if len(value) >= 2 and value[0] == value[-1] and (value[0] in {"'", '"'}):
        value = value[1:-1]
    if not NAME.fullmatch(value):
        raise SourceError("skill_name_invalid")
    return value
