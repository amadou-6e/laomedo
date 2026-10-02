"""Explicit, bounded provider-neutral orchestration. No credentials or model SDKs."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from uuid import uuid4
from .artifacts import selections


class HandoffError(ValueError):
    pass


def envelope(source, target, task, *, skills, execution_id=None, step=0,
             operation="fresh", artifacts=None):
    """Select answer/task explicitly; never copy the entire originating record."""
    if not isinstance(target, dict) or target.get("provider") not in {"codex", "opencode"}:
        raise HandoffError("invalid_target")
    if set(target) - {"provider", "agent", "model", "effort"}:
        raise HandoffError("unexpected_target_fields")
    if source is not None and source.get("status") != "completed":
        raise HandoffError("source_not_completed")
    if not isinstance(task, str) or not task.strip():
        raise HandoffError("task_required")
    if operation not in {"fresh", "resume"}:
        raise HandoffError("invalid_operation")
    if operation == "resume" and (not source or source.get("provider") != target["provider"]):
        raise HandoffError("foreign_or_missing_resume")
    if operation == "resume" and not all(source.get(k) for k in
                                         ("thread_id", "post_run_hash", "run_id")):
        raise HandoffError("resume_bindings_required")
    selected = selections(artifacts or [])
    if operation == "resume" and selected:
        raise HandoffError("resume_artifact_import_forbidden")
    if not isinstance(skills, list) or not 1 <= len(skills) <= 16:
        raise HandoffError("pinned_skills_required")
    clean_skills = []
    for skill in skills:
        if (not isinstance(skill, dict) or
                not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", str(skill.get("skill_id", ""))) or
                not re.fullmatch(r"sha256:[0-9a-f]{64}", str(skill.get("revision_id", ""))) or
                skill.get("tree_hash", skill["revision_id"]) != skill["revision_id"]):
            raise HandoffError("invalid_pinned_skill")
        clean_skills.append({"skill_id": skill["skill_id"], "revision_id": skill["revision_id"],
                             "tree_hash": skill["revision_id"]})
    if len({skill["skill_id"] for skill in clean_skills}) != len(clean_skills):
        raise HandoffError("duplicate_skill_id")
    if operation == "resume":
        prior_skills = source.get("skills")
        if not isinstance(prior_skills, list) or [(s.get("skill_id"), s.get("revision_id")) for s in prior_skills] != [
                (s["skill_id"], s["revision_id"]) for s in clean_skills]:
            raise HandoffError("resume_skill_binding_mismatch")
    return {"schema_version": 1, "execution_id": execution_id or str(uuid4()),
            "step": step, "source": None if source is None else {
                "provider": source.get("provider"), "run_id": source.get("run_id")},
            "target": deepcopy(target), "task": task, "skill_refs": clean_skills,
            "workspace_policy": "resume_bound" if operation == "resume" else "independent",
            "operation": operation, "artifacts": selected,
            "prior": None if operation == "fresh" else {k: source[k] for k in
                ("provider", "run_id", "thread_id", "post_run_hash", "model", "effort")}}


class BoundedController:
    """Bound dispatch attempts; remote execution may continue after timeout.

    Optional private state persists reservations before dispatch. Recovery exposes
    uncertain transitions without replay; no exactly-once restart claim.
    """
    def __init__(self, adapter, *, max_iterations, turn_budget, timeout_seconds,
                 clock=time.monotonic, state_dir=None):
        if any(type(v) is not int or v <= 0 for v in (max_iterations, turn_budget)):
            raise HandoffError("positive_iteration_and_turn_limits_required")
        if not 0 < timeout_seconds <= 86400:
            raise HandoffError("bounded_deadline_required")
        self.adapter, self.clock = adapter, clock
        self.max_iterations, self.turn_budget = max_iterations, turn_budget
        self.deadline = clock() + timeout_seconds
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.records = []
        self.submitted = 0
        self.execution_id = str(uuid4())
        self.started = False
        self.cancel_evidence = None
        self.stop_reason = None
        self.state_dir = None
        if state_dir is not None:
            root = Path(state_dir).resolve()
            if any((parent / ".git").exists() for parent in (root, *root.parents)):
                raise HandoffError("controller_state_must_be_outside_git")
            root.mkdir(parents=True, exist_ok=True)
            self.state_dir = root
            self._persist("prepared")

    def cancel(self):
        self.cancelled.set()
        try:
            evidence = self.adapter.cancel(self.execution_id)
        except Exception as exc:
            evidence = {"cancel_acknowledged": False, "error_type": type(exc).__name__}
        with self.state_lock:
            self.cancel_evidence = evidence
            self._persist(self.stop_reason or "cancel_requested")

    def run(self, targets, task, skills, *, success, loop=False, artifacts=None):
        if not self.lock.acquire(False):
            raise HandoffError("execution_busy")
        try:
            if self.started:
                raise HandoffError("execution_already_started")
            self.started = True
            if not targets or not callable(success):
                raise HandoffError("targets_and_stop_predicate_required")
            previous, seen = None, set()
            for step in range(self.max_iterations):
                reason = ("cancelled" if self.cancelled.is_set() else
                          "deadline" if self.clock() >= self.deadline else
                          "turn_budget" if self.submitted >= self.turn_budget else None)
                if reason:
                    return self._finish(reason)
                target = targets[step % len(targets)]
                try:
                    outgoing = envelope(previous, target, task, skills=skills,
                                        execution_id=self.execution_id, step=step,
                                        artifacts=(artifacts(previous) if callable(artifacts) else artifacts))
                except Exception as exc:
                    with self.state_lock:
                        self.records.append({"step": step, "status": "handoff_rejected",
                                             "error_type": type(exc).__name__, "run": None})
                    return self._finish("handoff_rejected")
                transition = {"handoff": outgoing, "status": "dispatching", "run": None}
                with self.state_lock:
                    self.records.append(transition)
                    # Reserve conservatively before submission, including uncertain sends.
                    self.submitted += 1
                    self._persist("dispatching")
                try:
                    result = self.adapter.dispatch(outgoing, deadline=self.deadline,
                                                   cancelled=self.cancelled)
                except Exception as exc:
                    with self.state_lock:
                        transition.update(status="uncertain", error_type=type(exc).__name__)
                    return self._finish("dispatch_uncertain")
                with self.state_lock:
                    transition.update(status=result.get("status"), run=deepcopy(result))
                    if result.get("status") == "rejected":
                        self.submitted -= 1
                    self._persist("running")
                if result.get("status") == "rejected":
                    return self._finish("dispatch_rejected")
                if self.cancelled.is_set():
                    return self._finish("cancelled")
                if self.clock() >= self.deadline:
                    return self._finish("deadline")
                if result.get("status") != "completed":
                    return self._finish("agent_failed")
                try:
                    accepted = success(result)
                except Exception as exc:
                    with self.state_lock:
                        transition["predicate_error_type"] = type(exc).__name__
                    return self._finish("stop_predicate_failed")
                if accepted:
                    return self._finish("success")
                answer = result.get("answer")
                if not isinstance(answer, str) or not answer.strip():
                    return self._finish("no_progress")
                if not loop and step + 1 == len(targets):
                    return self._finish("chain_completed")
                fingerprint = hashlib.sha256(answer.encode()).hexdigest()
                if fingerprint in seen:
                    return self._finish("no_progress")
                seen.add(fingerprint)
                previous, task = result, answer
            return self._finish("iteration_limit")
        finally:
            self.lock.release()

    def _finish(self, reason):
        with self.state_lock:
            self.stop_reason = reason
            result = {"execution_id": self.execution_id, "stop_reason": reason,
                    "submitted_turns": self.submitted, "transitions": deepcopy(self.records),
                    "cancel_evidence": deepcopy(self.cancel_evidence)}
            self._persist(reason)
            return result

    def _persist(self, status):
        with self.state_lock:
            if self.state_dir is None:
                return
            path = self.state_dir / (self.execution_id + ".json")
            pending = path.with_suffix(".pending-" + uuid4().hex)
            value = {"execution_id": self.execution_id, "stop_reason": status,
                     "submitted_turns": self.submitted, "transitions": deepcopy(self.records),
                     "cancel_evidence": deepcopy(self.cancel_evidence),
                     "limits": {"max_iterations": self.max_iterations, "turn_budget": self.turn_budget}}
            pending.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            os.replace(pending, path)

    @staticmethod
    def inspect(state_dir, execution_id):
        from uuid import UUID
        if str(UUID(execution_id)) != execution_id:
            raise HandoffError("invalid_execution_id")
        result = json.loads((Path(state_dir) / (execution_id + ".json")).read_text(encoding="utf-8"))
        if result["stop_reason"] in {"dispatching", "running", "cancel_requested"}:
            result["recovery_status"] = "interrupted_or_uncertain; never automatically replay"
        return result
