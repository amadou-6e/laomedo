"""Deterministic Skill Draft boundary probe for specs issue #122.

This validates drafts after a synthetic edit. It is not an OS write sandbox:
rejection after a write does not prove that a forbidden write was prevented.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Callable
from uuid import uuid4


BASE_SKILL = ("---\nname: fixture-draft-122\n"
              "description: Synthetic editing fixture.\n---\n\n"
              "Rule: answer with the word amber.\n")
POLICY = json.loads(Path(__file__).with_name("edit-policy.json").read_text(
    encoding="utf-8"))


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def policy_ref() -> dict:
    encoded = json.dumps(POLICY, sort_keys=True, separators=(",", ":")).encode()
    return {"policy_id": POLICY["policy_id"],
            "revision_id": POLICY["revision_id"], "hash": sha256(encoded)}


def inventory(root: Path) -> dict[str, bytes]:
    """Reject links and special files; never read through a symlink."""
    is_junction = getattr(root, "is_junction", lambda: False)
    if root.is_symlink() or is_junction() or not root.is_dir():
        raise ValueError("invalid_tree_root")
    files = {}
    allowed_dirs = {str(PurePosixPath(path).parent) for path in POLICY["allowed_paths"]}
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            path = Path(parent) / name
            junction = getattr(path, "is_junction", lambda: False)
            if path.is_symlink() or junction():
                raise ValueError("link_or_junction_in_tree")
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                if relative not in allowed_dirs:
                    raise ValueError("unapproved_directory")
                continue
            if not path.is_file():
                raise ValueError("special_file_in_tree")
            files[relative] = path.read_bytes()
    return files


def tree_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(files.items()):
        encoded = relative.encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def path_allowed(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (not path.is_absolute() and ".." not in path.parts
            and relative in POLICY["allowed_paths"]
            and path.suffix in POLICY["allowed_suffixes"])


def structural_validation(base: dict[str, bytes], draft: dict[str, bytes]) -> list[str]:
    errors = []
    changed = sorted(key for key in base.keys() | draft.keys()
                     if base.get(key) != draft.get(key))
    if len(draft) > POLICY["max_files"]:
        errors.append("too_many_files")
    for relative in changed:
        if not path_allowed(relative):
            errors.append("forbidden_path")
        if relative not in base and not POLICY["allow_new_files"]:
            errors.append("new_file_forbidden")
    for relative, data in draft.items():
        if len(data) > POLICY["max_file_bytes"]:
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
        for field in POLICY["required_frontmatter"]:
            if not any(line.startswith(field + ": ") for line in frontmatter.splitlines()):
                errors.append("frontmatter_field_missing")
    if "SKILL.md" not in draft:
        errors.append("skill_missing")
    return sorted(set(errors))


def fixed_case_evaluation(files: dict[str, bytes]) -> dict:
    """Checks fixture content only; it does not judge model output quality."""
    content = files.get("SKILL.md", b"").decode("utf-8", errors="replace")
    return {"kind": "deterministic_fixture", "case_id": "contains-amber-rule",
            "passed": "Rule: answer with the word amber." in content}


def patch_for(base: dict[str, bytes], draft: dict[str, bytes]) -> str:
    chunks = []
    for relative in sorted(base.keys() | draft.keys()):
        old = base.get(relative, b"").decode("utf-8", errors="replace").replace(
            "\r\n", "\n").splitlines(True)
        new = draft.get(relative, b"").decode("utf-8", errors="replace").replace(
            "\r\n", "\n").splitlines(True)
        if old == new:
            continue
        chunks.extend(difflib.unified_diff(old, new, fromfile="base/" + relative,
                                           tofile="draft/" + relative))
    return "".join(chunks)


def snapshot(root: Path, destination: Path) -> str:
    if destination.exists():
        raise FileExistsError("snapshot_exists")
    original = inventory(root)
    shutil.copytree(root, destination)
    if tree_hash(inventory(destination)) != tree_hash(original):
        raise ValueError("snapshot_hash_mismatch")
    return tree_hash(original)


def restore(snapshot_dir: Path, draft_dir: Path, expected_hash: str,
            allowed_root: Path) -> str:
    if not snapshot_dir.is_dir() or tree_hash(inventory(snapshot_dir)) != expected_hash:
        raise ValueError("post_run_snapshot_unavailable")
    inventory(draft_dir)
    root = allowed_root.resolve(strict=True)
    draft = draft_dir.resolve(strict=True)
    frozen = snapshot_dir.resolve(strict=True)
    if (draft == root or frozen == root or
            not draft.is_relative_to(root) or
            not frozen.is_relative_to(root)):
        raise ValueError("restore_path_outside_run_root")
    if draft == frozen:
        raise ValueError("snapshot_equals_draft")
    shutil.rmtree(draft_dir)
    shutil.copytree(snapshot_dir, draft_dir)
    return tree_hash(inventory(draft_dir))


def evaluate_edit(case_name: str, edit: Callable[[Path], None], root: Path,
                  base_revision: str = "1", current_revision: str = "1") -> dict:
    canonical = root / "canonical"
    draft = root / "draft"
    canonical.mkdir()
    (canonical / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
    base = inventory(canonical)
    base_hash = tree_hash(base)
    shutil.copytree(canonical, draft)
    agent_outcome = "completed"
    edit_error_class = None
    try:
        edit(draft)
    except TimeoutError:
        agent_outcome = "timeout"
        edit_error_class = "TimeoutError"
    except Exception as exc:
        agent_outcome = "partial_failure"
        edit_error_class = type(exc).__name__
    violations = []
    try:
        proposed = inventory(draft)
    except ValueError as exc:
        proposed = {}
        violations.append(str(exc))
    violations += structural_validation(base, proposed)
    base_after = tree_hash(inventory(canonical))
    if base_after != base_hash:
        violations.append("canonical_changed")
    changed = sorted(key for key in base.keys() | proposed.keys()
                     if base.get(key) != proposed.get(key))
    if not changed:
        violations.append("no_change")
    if current_revision != base_revision:
        violations.append("base_revision_conflict")
    eligible = agent_outcome == "completed" and not violations
    return {
        "case": case_name, "draft_id": str(uuid4()),
        "base_ref": {"revision_id": base_revision, "tree_hash": base_hash},
        "draft_ref": {"tree_hash": tree_hash(proposed) if proposed else None},
        "policy_ref": policy_ref(), "agent_run_id": None, "trace_ref": None,
        "agent_outcome": agent_outcome, "edit_error_class": edit_error_class,
        "changed_paths": changed,
        "patch": patch_for(base, proposed) if proposed else None,
        "validation": {"kind": "deterministic", "errors": sorted(set(violations))},
        "evaluation": {"base": fixed_case_evaluation(base),
                       "draft": fixed_case_evaluation(proposed)},
        "canonical_unchanged": base_after == base_hash,
        "promotion_eligible": eligible,
        "promotion_performed": False,
    }


def run_cases() -> dict:
    results = {}
    with tempfile.TemporaryDirectory(prefix="laomedo-122-") as temporary:
        root = Path(temporary)
        def case(name, edit, **kwargs):
            home = root / name
            home.mkdir()
            results[name] = evaluate_edit(name, edit, home, **kwargs)

        case("allowed_edit", lambda draft: (draft / "SKILL.md").write_text(
            BASE_SKILL + "Example: say amber.\n", encoding="utf-8"))
        case("forbidden_path", lambda draft: (draft / "secret.txt").write_text(
            "synthetic", encoding="utf-8"))
        case("partial_failure", lambda draft: (
            (draft / "SKILL.md").write_text(BASE_SKILL + "Partial.\n", encoding="utf-8"),
            (_ for _ in ()).throw(RuntimeError("synthetic failure"))))
        case("timeout", lambda draft: (
            (draft / "SKILL.md").write_text(BASE_SKILL + "Partial.\n", encoding="utf-8"),
            (_ for _ in ()).throw(TimeoutError())))
        case("concurrent_base_change", lambda draft: (draft / "SKILL.md").write_text(
            BASE_SKILL + "Allowed change.\n", encoding="utf-8"),
            current_revision="2")
        link_home = root / "escaping_symlink"
        link_home.mkdir()
        outside = link_home / "outside"
        outside.mkdir()
        def link_edit(draft):
            (draft / "examples").symlink_to(outside, target_is_directory=True)
        results["escaping_symlink"] = evaluate_edit(
            "escaping_symlink", link_edit, link_home)
        if results["escaping_symlink"]["edit_error_class"] in (
                "OSError", "PermissionError", "NotImplementedError"):
            results["escaping_symlink"]["status"] = "unsupported_on_host"
        resume_home = root / "resume"
        resume_home.mkdir()
        draft = resume_home / "draft"
        draft.mkdir()
        (draft / "SKILL.md").write_text(BASE_SKILL + "Post-run line.\n", encoding="utf-8")
        frozen = resume_home / "snapshot"
        post_run_hash = snapshot(draft, frozen)
        (draft / "SKILL.md").write_text(BASE_SKILL + "Drift line.\n", encoding="utf-8")
        before_missing = tree_hash(inventory(draft))
        try:
            restore(resume_home / "missing", draft, post_run_hash, resume_home)
            missing_refused = False
        except ValueError:
            missing_refused = tree_hash(inventory(draft)) == before_missing
        restored_hash = restore(frozen, draft, post_run_hash, resume_home)
        results["resume"] = {"missing_snapshot_refused_before_change": missing_refused,
                             "restored_last_post_run_hash": restored_hash == post_run_hash,
                             "post_run_content_visible": "Post-run line." in
                             (draft / "SKILL.md").read_text(encoding="utf-8")}
    return {"policy_ref": policy_ref(), "cases": results,
            "model_calls": 0, "credential_used": False,
            "enforcement_scope": "post_edit_validation_only"}


if __name__ == "__main__":
    report = run_cases()
    # Reports contain only synthetic fixture content and hashes.
    print(json.dumps(report, indent=2))
