"""Registry files; existing admission and byte behavior are preserved."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import json
import os
import stat
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.paths import validate_relative_path


def is_link(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def inventory(root: Path) -> dict[str, bytes]:
    """Read regular files only; reject links, junctions, and special files."""
    if is_link(root) or not root.is_dir():
        raise SkillStoreError("invalid_tree_root")
    files = {}
    folders = []
    for parent, directories, names in os.walk(root, followlinks=False):
        for name in sorted(directories + names):
            path = Path(parent) / name
            if is_link(path):
                raise SkillStoreError("linked_path")
            if path.is_dir():
                folders.append(path.relative_to(root).as_posix())
                continue
            if not path.is_file():
                raise SkillStoreError("special_file")
            if path.stat().st_nlink > 1:
                raise SkillStoreError("hardlinked_file")
            relative = path.relative_to(root).as_posix()
            validate_relative_path(relative)
            files[relative] = path.read_bytes()
    if "SKILL.md" not in files:
        raise SkillStoreError("missing_skill_file")
    if any(
        not any(name.startswith(folder + "/") for name in files) for folder in folders
    ):
        raise SkillStoreError("empty_directory")
    return files


def write_json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    pending.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    os.replace(pending, path)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SkillStoreError("invalid_record")
    return value
