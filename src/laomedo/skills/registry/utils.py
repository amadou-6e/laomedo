"""Validate registry content, policies and immutable tree identities."""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath
from uuid import uuid4
import difflib
import hashlib
import json
import laomedo.skills.registry.settings as _registry_settings
import laomedo.skills.registry.errors as _registry_errors
import os
import stat


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_name(value: str) -> str:
    if not isinstance(value, str) or not _registry_settings.NAME.fullmatch(value):
        raise _registry_errors.SkillStoreError("invalid_skill_id")
    return value


def _safe_relative(value: str) -> str:
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise _registry_errors.SkillStoreError("unsafe_relative_path")
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or ":" in value
        or any(part in (".", "..") for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise _registry_errors.SkillStoreError("unsafe_relative_path")
    return value


def _is_link(path: Path) -> bool:
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
    if _is_link(root) or not root.is_dir():
        raise _registry_errors.SkillStoreError("invalid_tree_root")
    files = {}
    folders = []
    for parent, directories, names in os.walk(root, followlinks=False):
        for name in sorted(directories + names):
            path = Path(parent) / name
            if _is_link(path):
                raise _registry_errors.SkillStoreError("linked_path")
            if path.is_dir():
                folders.append(path.relative_to(root).as_posix())
                continue
            if not path.is_file():
                raise _registry_errors.SkillStoreError("special_file")
            if path.stat().st_nlink > 1:
                raise _registry_errors.SkillStoreError("hardlinked_file")
            relative = path.relative_to(root).as_posix()
            _safe_relative(relative)
            files[relative] = path.read_bytes()
    if "SKILL.md" not in files:
        raise _registry_errors.SkillStoreError("missing_skill_file")
    if any(
        not any(name.startswith(folder + "/") for name in files) for folder in folders
    ):
        raise _registry_errors.SkillStoreError("empty_directory")
    return files


def tree_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(files.items()):
        encoded = _safe_relative(relative).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def file_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {path: _hash(data) for path, data in sorted(files.items())}


def validate_policy(policy: dict) -> dict:
    required = (
        "policy_id",
        "revision_id",
        "allowed_paths",
        "allowed_suffixes",
        "allow_new_files",
        "allow_deletions",
        "allow_scripts",
        "allow_dependencies",
        "allow_assets",
        "required_frontmatter",
        "permitted_validation_commands",
        "max_files",
        "max_file_bytes",
    )
    if not isinstance(policy, dict) or any(key not in policy for key in required):
        raise _registry_errors.SkillStoreError("invalid_policy")
    _safe_name(policy["policy_id"])
    if not isinstance(policy["revision_id"], str) or not policy["revision_id"]:
        raise _registry_errors.SkillStoreError("invalid_policy_revision")
    paths = policy["allowed_paths"]
    if (
        not isinstance(paths, list)
        or not paths
        or any(not isinstance(path, str) for path in paths)
    ):
        raise _registry_errors.SkillStoreError("invalid_allowed_paths")
    for path in paths:
        _safe_relative(path)
    if len(paths) != len(set(paths)) or "SKILL.md" not in paths:
        raise _registry_errors.SkillStoreError("invalid_allowed_paths")
    suffixes = policy["allowed_suffixes"]
    if (
        not isinstance(suffixes, list)
        or not suffixes
        or any(
            not isinstance(item, str) or not item.startswith(".") for item in suffixes
        )
    ):
        raise _registry_errors.SkillStoreError("invalid_suffixes")
    for key in (
        "allow_new_files",
        "allow_deletions",
        "allow_scripts",
        "allow_dependencies",
        "allow_assets",
    ):
        if not isinstance(policy[key], bool):
            raise _registry_errors.SkillStoreError("invalid_policy_boolean")
    safe_documents = {".md", ".txt", ".json", ".yaml", ".yml"}
    safe_assets = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf"}
    script_suffixes = {
        ".py",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".sh",
        ".ps1",
        ".bat",
        ".cmd",
        ".rb",
        ".pl",
        ".php",
    }
    if not policy["allow_scripts"] and any(
        "scripts" in PurePosixPath(path).parts
        or PurePosixPath(path).suffix.lower()
        not in (safe_documents | (safe_assets if policy["allow_assets"] else set()))
        for path in paths
    ):
        raise _registry_errors.SkillStoreError("policy_grants_disallowed_scripts")
    if not policy["allow_dependencies"] and any(
        PurePosixPath(path).name
        in ("requirements.txt", "package.json", "pyproject.toml", "Pipfile")
        for path in paths
    ):
        raise _registry_errors.SkillStoreError("policy_grants_disallowed_dependencies")
    if not policy["allow_assets"] and any(
        PurePosixPath(path).suffix.lower()
        not in (
            safe_documents | (script_suffixes if policy["allow_scripts"] else set())
        )
        for path in paths
    ):
        raise _registry_errors.SkillStoreError("policy_grants_disallowed_assets")
    for key in ("required_frontmatter", "permitted_validation_commands"):
        if not isinstance(policy[key], list) or not all(
            isinstance(item, str) for item in policy[key]
        ):
            raise _registry_errors.SkillStoreError("invalid_policy_list")
    for key in ("max_files", "max_file_bytes"):
        if (
            not isinstance(policy[key], int)
            or isinstance(policy[key], bool)
            or policy[key] <= 0
        ):
            raise _registry_errors.SkillStoreError("invalid_policy_limit")
    return {
        "policy_id": policy["policy_id"],
        "revision_id": policy["revision_id"],
        "hash": _hash(_canonical_json(policy)),
    }


def validate_draft(
    base: dict[str, bytes], draft: dict[str, bytes], policy: dict
) -> list[str]:
    validate_policy(policy)
    errors = []
    if len(draft) > policy["max_files"]:
        errors.append("too_many_files")
    changed = {
        key for key in base.keys() | draft.keys() if base.get(key) != draft.get(key)
    }
    for relative in changed:
        if (
            relative not in policy["allowed_paths"]
            or PurePosixPath(relative).suffix not in policy["allowed_suffixes"]
        ):
            errors.append("forbidden_path")
        if relative not in base and not policy["allow_new_files"]:
            errors.append("new_file_forbidden")
        if relative not in draft and not policy["allow_deletions"]:
            errors.append("deletion_forbidden")
        if relative in draft:
            try:
                draft[relative].decode("utf-8")
            except UnicodeDecodeError:
                errors.append("non_utf8_changed_file")
    for relative, data in draft.items():
        if len(data) > policy["max_file_bytes"]:
            errors.append("file_too_large")
        if relative != "SKILL.md":
            continue
        try:
            content = data.decode("utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            errors.append("skill_not_utf8")
            continue
        if not content.startswith("---\n") or "\n---\n" not in content[4:]:
            errors.append("frontmatter_missing")
            continue
        frontmatter = content.split("\n---\n", 1)[0]
        for field in policy["required_frontmatter"]:
            if not any(
                line.startswith(field + ": ") and line.split(":", 1)[1].strip()
                for line in frontmatter.splitlines()
            ):
                errors.append("frontmatter_field_missing")
    return sorted(set(errors))


def patch_for(base: dict[str, bytes], draft: dict[str, bytes]) -> str:
    chunks = []
    for relative in sorted(base.keys() | draft.keys()):
        if base.get(relative) == draft.get(relative):
            continue
        try:
            before = base.get(relative, b"").decode("utf-8")
            after = draft.get(relative, b"").decode("utf-8")
        except UnicodeDecodeError:
            chunks.append(f"--- base/{relative}\n+++ draft/{relative}\n")
            chunks.append(f"-bytes {base.get(relative, b'')!r}\n")
            chunks.append(f"+bytes {draft.get(relative, b'')!r}\n")
            continue

        def exact_lines(value: str) -> list[str]:
            return [
                line.encode("unicode_escape").decode("ascii") + "\n"
                for line in value.splitlines(keepends=True)
            ]

        chunks.extend(
            difflib.unified_diff(
                exact_lines(before),
                exact_lines(after),
                fromfile="base/" + relative,
                tofile="draft/" + relative,
            )
        )
    return "".join(chunks)


def _write_json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    pending.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    os.replace(pending, path)


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise _registry_errors.SkillStoreError("invalid_record")
    return value
