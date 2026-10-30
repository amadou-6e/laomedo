"""Registry policy; existing admission and byte behavior are preserved."""

from __future__ import annotations

from pathlib import PurePosixPath
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.hashing import canonical_json, hash_bytes
from laomedo.skills.registry.paths import validate_name, validate_relative_path


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
        raise SkillStoreError("invalid_policy")
    validate_name(policy["policy_id"])
    if not isinstance(policy["revision_id"], str) or not policy["revision_id"]:
        raise SkillStoreError("invalid_policy_revision")
    paths = policy["allowed_paths"]
    if (
        not isinstance(paths, list)
        or not paths
        or any(not isinstance(path, str) for path in paths)
    ):
        raise SkillStoreError("invalid_allowed_paths")
    for path in paths:
        validate_relative_path(path)
    if len(paths) != len(set(paths)) or "SKILL.md" not in paths:
        raise SkillStoreError("invalid_allowed_paths")
    suffixes = policy["allowed_suffixes"]
    if (
        not isinstance(suffixes, list)
        or not suffixes
        or any(
            not isinstance(item, str) or not item.startswith(".") for item in suffixes
        )
    ):
        raise SkillStoreError("invalid_suffixes")
    for key in (
        "allow_new_files",
        "allow_deletions",
        "allow_scripts",
        "allow_dependencies",
        "allow_assets",
    ):
        if not isinstance(policy[key], bool):
            raise SkillStoreError("invalid_policy_boolean")
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
        raise SkillStoreError("policy_grants_disallowed_scripts")
    if not policy["allow_dependencies"] and any(
        PurePosixPath(path).name
        in ("requirements.txt", "package.json", "pyproject.toml", "Pipfile")
        for path in paths
    ):
        raise SkillStoreError("policy_grants_disallowed_dependencies")
    if not policy["allow_assets"] and any(
        PurePosixPath(path).suffix.lower()
        not in (
            safe_documents | (script_suffixes if policy["allow_scripts"] else set())
        )
        for path in paths
    ):
        raise SkillStoreError("policy_grants_disallowed_assets")
    for key in ("required_frontmatter", "permitted_validation_commands"):
        if not isinstance(policy[key], list) or not all(
            isinstance(item, str) for item in policy[key]
        ):
            raise SkillStoreError("invalid_policy_list")
    for key in ("max_files", "max_file_bytes"):
        if (
            not isinstance(policy[key], int)
            or isinstance(policy[key], bool)
            or policy[key] <= 0
        ):
            raise SkillStoreError("invalid_policy_limit")
    return {
        "policy_id": policy["policy_id"],
        "revision_id": policy["revision_id"],
        "hash": hash_bytes(canonical_json(policy)),
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
