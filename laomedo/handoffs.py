"""Explicit, bounded provider-neutral orchestration. No credentials or model SDKs."""
from copy import deepcopy
import hashlib
import re
import threading
import time
from uuid import uuid4


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
    selected = deepcopy(artifacts or [])
    if selected:
        # Existing runners have no audited selected-file import interface.
        raise HandoffError("artifact_transfer_not_supported")
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
    return {"schema_version": 1, "execution_id": execution_id or str(uuid4()),
            "step": step, "source": None if source is None else {
                "provider": source.get("provider"), "run_id": source.get("run_id")},
            "target": deepcopy(target), "task": task, "skill_refs": clean_skills,
            "workspace_policy": "resume_bound" if operation == "resume" else "independent",
            "operation": operation, "artifacts": selected,
            "prior": None if operation == "fresh" else {k: source[k] for k in
                ("provider", "run_id", "thread_id", "post_run_hash", "model", "effort")}}


class BoundedController:
    """An adapter must honor deadline/cancellation; no automatic retries.

    State is in-memory. Retain result for inspection but do not claim durable
    exactly-once execution across process restart or reconnect.
    """
    def __init__(self, adapter, *, max_iterations, turn_budget, timeout_seconds,
                 clock=time.monotonic):
        if any(type(v) is not int or v <= 0 for v in (max_iterations, turn_budget)):
            raise HandoffError("positive_iteration_and_turn_limits_required")
        if not 0 < timeout_seconds <= 86400:
            raise HandoffError("bounded_deadline_required")
        self.adapter, self.clock = adapter, clock
        self.max_iterations, self.turn_budget = max_iterations, turn_budget
        self.deadline = clock() + timeout_seconds
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.records = []
        self.submitted = 0
        self.execution_id = str(uuid4())
        self.started = False
        self.cancel_evidence = None

    def cancel(self):
        self.cancelled.set()
        try:
            self.cancel_evidence = self.adapter.cancel(self.execution_id)
        except Exception as exc:
            self.cancel_evidence = {"cancel_acknowledged": False,
                                    "error_type": type(exc).__name__}

    def run(self, targets, task, skills, *, success, loop=False):
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
                outgoing = envelope(previous, target, task, skills=skills,
                                    execution_id=self.execution_id, step=step)
                transition = {"handoff": outgoing, "status": "dispatching", "run": None}
                self.records.append(transition)
                # Reserve conservatively before submission, including uncertain sends.
                self.submitted += 1
                try:
                    result = self.adapter.dispatch(outgoing, deadline=self.deadline,
                                                   cancelled=self.cancelled)
                except Exception as exc:
                    transition.update(status="uncertain", error_type=type(exc).__name__)
                    return self._finish("dispatch_uncertain")
                transition.update(status=result.get("status"), run=deepcopy(result))
                if self.cancelled.is_set():
                    return self._finish("cancelled")
                if self.clock() >= self.deadline:
                    return self._finish("deadline")
                if result.get("status") != "completed":
                    return self._finish("agent_failed")
                try:
                    accepted = success(result)
                except Exception as exc:
                    transition["predicate_error_type"] = type(exc).__name__
                    return self._finish("stop_predicate_failed")
                if accepted:
                    return self._finish("success")
                answer = result.get("answer")
                if not isinstance(answer, str) or not answer.strip():
                    return self._finish("no_progress")
                fingerprint = hashlib.sha256(answer.encode()).hexdigest()
                if fingerprint in seen:
                    return self._finish("no_progress")
                seen.add(fingerprint)
                previous, task = result, answer
                if not loop and step + 1 == len(targets):
                    return self._finish("chain_completed")
            return self._finish("iteration_limit")
        finally:
            self.lock.release()

    def _finish(self, reason):
        return {"execution_id": self.execution_id, "stop_reason": reason,
                "submitted_turns": self.submitted, "transitions": deepcopy(self.records),
                "cancel_evidence": deepcopy(self.cancel_evidence)}
