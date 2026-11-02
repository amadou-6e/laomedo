"""Exact run-local skill exclusions and immutable materialization validation."""

from __future__ import annotations

from pathlib import Path
import hashlib
import os

from laomedo.agents.workspaces.skills.errors import WorkspaceSkillError
from laomedo.skills.registry.files import inventory, is_link
from laomedo.skills.registry.hashing import tree_hash
from laomedo.skills.registry.settings import NAME


def _exclude(workspace: Path):
    git = workspace / ".git"
    if not git.exists():
        return None
    if not git.is_dir() or is_link(git):
        raise WorkspaceSkillError("external_git_directory_unsupported")
    # Inspect entry metadata only, not Git object contents.
    for parent, dirs, names in os.walk(git, followlinks=False):
        for name in dirs + names:
            item = Path(parent) / name
            if (
                is_link(item)
                or not (item.is_dir() or item.is_file())
                or (item.is_file() and item.stat().st_nlink > 1)
            ):
                raise WorkspaceSkillError("unsafe_git_metadata")
    return git / "info" / "exclude"


def install(workspace: Path, skills: list[dict]) -> dict:
    for skill in skills:
        if not NAME.fullmatch(skill["skill_id"]):
            raise WorkspaceSkillError("invalid_skill_id")
    exclude = _exclude(workspace)
    if exclude is None:
        return {"enabled": False}
    exclude.parent.mkdir(exist_ok=True)
    original = exclude.read_bytes() if exclude.exists() else b""
    rules = [f"/.agents/skills/{skill['skill_id']}/" for skill in skills]
    addition = "\n".join(rules).encode("ascii") + b"\n"
    prefix = original + (b"\n" if original and not original.endswith(b"\n") else b"")
    exclude.write_bytes(prefix + addition)
    return {
        "enabled": True,
        "rules": rules,
        "exclude_sha256": hashlib.sha256(exclude.read_bytes()).hexdigest(),
    }


def verify(workspace: Path, skills: list[dict], exclusion: dict) -> None:
    for parent in (workspace / ".agents", workspace / ".agents" / "skills"):
        if is_link(parent) or not parent.is_dir():
            raise WorkspaceSkillError("unsafe_materialized_skill_path")
    if {entry.name for entry in (workspace / ".agents" / "skills").iterdir()} != {
        skill["skill_id"] for skill in skills
    }:
        raise WorkspaceSkillError("unexpected_materialized_skill")
    for skill in skills:
        if not NAME.fullmatch(skill["skill_id"]):
            raise WorkspaceSkillError("invalid_skill_id")
        if (
            tree_hash(inventory(workspace / ".agents" / "skills" / skill["skill_id"]))
            != skill["tree_hash"]
        ):
            raise WorkspaceSkillError("materialized_skill_mismatch")
    exclude = _exclude(workspace)
    if exclusion.get("enabled"):
        if (
            exclude is None
            or not exclude.is_file()
            or hashlib.sha256(exclude.read_bytes()).hexdigest()
            != exclusion["exclude_sha256"]
        ):
            raise WorkspaceSkillError("skill_git_exclusion_changed")
    elif exclude is not None:
        raise WorkspaceSkillError("skill_git_exclusion_changed")
