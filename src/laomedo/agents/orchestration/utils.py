"""Implementation owned by agents / handoffs / utils."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4
import laomedo.agents.artifacts.utils as _artifacts_utils
import laomedo.agents.orchestration.errors as _handoffs_errors
import re


def envelope(
    source,
    target,
    task,
    *,
    skills,
    execution_id=None,
    step=0,
    operation="fresh",
    artifacts=None,
):
    """Select answer/task explicitly; never copy the entire originating record."""
    if not isinstance(target, dict) or target.get("provider") not in {
        "codex",
        "opencode",
        "claude",
    }:
        raise _handoffs_errors.HandoffError("invalid_target")
    if set(target) - {"provider", "agent", "model", "effort"}:
        raise _handoffs_errors.HandoffError("unexpected_target_fields")
    if source is not None and source.get("status") != "completed":
        raise _handoffs_errors.HandoffError("source_not_completed")
    if not isinstance(task, str) or not task.strip():
        raise _handoffs_errors.HandoffError("task_required")
    if operation not in {"fresh", "resume"}:
        raise _handoffs_errors.HandoffError("invalid_operation")
    if operation == "resume" and (
        not source or source.get("provider") != target["provider"]
    ):
        raise _handoffs_errors.HandoffError("foreign_or_missing_resume")
    if operation == "resume" and not all(
        source.get(k) for k in ("thread_id", "post_run_hash", "run_id")
    ):
        raise _handoffs_errors.HandoffError("resume_bindings_required")
    selected = _artifacts_utils.selections(artifacts or [])
    if operation == "resume" and selected:
        raise _handoffs_errors.HandoffError("resume_artifact_import_forbidden")
    if not isinstance(skills, list) or not 0 <= len(skills) <= 16:
        raise _handoffs_errors.HandoffError("pinned_skills_required")
    clean_skills = []
    for skill in skills:
        if (
            not isinstance(skill, dict)
            or not re.fullmatch(
                r"[a-z0-9][a-z0-9_-]{0,63}", str(skill.get("skill_id", ""))
            )
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(skill.get("revision_id", ""))
            )
            or skill.get("tree_hash", skill["revision_id"]) != skill["revision_id"]
        ):
            raise _handoffs_errors.HandoffError("invalid_pinned_skill")
        clean_skills.append(
            {
                "skill_id": skill["skill_id"],
                "revision_id": skill["revision_id"],
                "tree_hash": skill["revision_id"],
            }
        )
    if len({skill["skill_id"] for skill in clean_skills}) != len(clean_skills):
        raise _handoffs_errors.HandoffError("duplicate_skill_id")
    if operation == "resume":
        prior_skills = source.get("skills")
        if not isinstance(prior_skills, list) or [
            (s.get("skill_id"), s.get("revision_id")) for s in prior_skills
        ] != [(s["skill_id"], s["revision_id"]) for s in clean_skills]:
            raise _handoffs_errors.HandoffError("resume_skill_binding_mismatch")
    return {
        "schema_version": 1,
        "execution_id": execution_id or str(uuid4()),
        "step": step,
        "source": (
            None
            if source is None
            else {"provider": source.get("provider"), "run_id": source.get("run_id")}
        ),
        "target": deepcopy(target),
        "task": task,
        "skill_refs": clean_skills,
        "workspace_policy": "resume_bound" if operation == "resume" else "independent",
        "operation": operation,
        "artifacts": selected,
        "prior": (
            None
            if operation == "fresh"
            else {
                k: source[k]
                for k in (
                    "provider",
                    "run_id",
                    "thread_id",
                    "post_run_hash",
                    "model",
                    "effort",
                )
            }
        ),
    }
