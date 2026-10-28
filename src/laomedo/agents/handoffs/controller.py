"""Explicit, bounded provider-neutral orchestration. No credentials or model SDKs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import laomedo.agents.handoffs.errors as _handoffs_errors
import laomedo.agents.handoffs.utils as _handoffs_utils
import os
import threading
import time


class BoundedController:
    """Bound dispatch attempts; remote execution may continue after timeout.

    Optional private state persists reservations before dispatch. Recovery exposes
    uncertain transitions without replay; no exactly-once restart claim.
    """

    def __init__(
        self,
        adapter,
        *,
        max_iterations,
        turn_budget,
        timeout_seconds,
        clock=time.monotonic,
        state_dir=None,
    ):
        if any(type(v) is not int or v <= 0 for v in (max_iterations, turn_budget)):
            raise _handoffs_errors.HandoffError(
                "positive_iteration_and_turn_limits_required"
            )
        if not 0 < timeout_seconds <= 86400:
            raise _handoffs_errors.HandoffError("bounded_deadline_required")
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
                raise _handoffs_errors.HandoffError(
                    "controller_state_must_be_outside_git"
                )
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
            raise _handoffs_errors.HandoffError("execution_busy")
        try:
            if self.started:
                raise _handoffs_errors.HandoffError("execution_already_started")
            self.started = True
            if not targets or not callable(success):
                raise _handoffs_errors.HandoffError(
                    "targets_and_stop_predicate_required"
                )
            previous, seen = None, set()
            for step in range(self.max_iterations):
                reason = (
                    "cancelled"
                    if self.cancelled.is_set()
                    else (
                        "deadline"
                        if self.clock() >= self.deadline
                        else (
                            "turn_budget"
                            if self.submitted >= self.turn_budget
                            else None
                        )
                    )
                )
                if reason:
                    return self._finish(reason)
                target = targets[step % len(targets)]
                try:
                    outgoing = _handoffs_utils.envelope(
                        previous,
                        target,
                        task,
                        skills=skills,
                        execution_id=self.execution_id,
                        step=step,
                        artifacts=(
                            artifacts(previous) if callable(artifacts) else artifacts
                        ),
                    )
                except Exception as exc:
                    with self.state_lock:
                        self.records.append(
                            {
                                "step": step,
                                "status": "handoff_rejected",
                                "error_type": type(exc).__name__,
                                "run": None,
                            }
                        )
                    return self._finish("handoff_rejected")
                transition = {"handoff": outgoing, "status": "dispatching", "run": None}
                with self.state_lock:
                    self.records.append(transition)
                    # Reserve conservatively before submission, including uncertain sends.
                    self.submitted += 1
                    self._persist("dispatching")
                try:

                    def record_ack(ack):
                        with self.state_lock:
                            transition.update(
                                status="runner_acknowledged",
                                run={
                                    "provider": target["provider"],
                                    "run_id": ack["run_id"],
                                    "status": ack.get("status"),
                                },
                            )
                            self._persist("running")

                    result = self.adapter.dispatch(
                        outgoing,
                        deadline=self.deadline,
                        cancelled=self.cancelled,
                        early_start=True,
                        on_ack=record_ack,
                    )
                except Exception as exc:
                    with self.state_lock:
                        transition.update(
                            status="uncertain", error_type=type(exc).__name__
                        )
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
            result = {
                "execution_id": self.execution_id,
                "stop_reason": reason,
                "submitted_turns": self.submitted,
                "transitions": deepcopy(self.records),
                "cancel_evidence": deepcopy(self.cancel_evidence),
            }
            self._persist(reason)
            return result

    def _persist(self, status):
        with self.state_lock:
            if self.state_dir is None:
                return
            path = self.state_dir / (self.execution_id + ".json")
            pending = path.with_suffix(".pending-" + uuid4().hex)
            value = {
                "execution_id": self.execution_id,
                "stop_reason": status,
                "submitted_turns": self.submitted,
                "transitions": deepcopy(self.records),
                "cancel_evidence": deepcopy(self.cancel_evidence),
                "limits": {
                    "max_iterations": self.max_iterations,
                    "turn_budget": self.turn_budget,
                },
            }
            pending.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            os.replace(pending, path)

    @staticmethod
    def inspect(state_dir, execution_id):
        from uuid import UUID

        if str(UUID(execution_id)) != execution_id:
            raise _handoffs_errors.HandoffError("invalid_execution_id")
        result = json.loads(
            (Path(state_dir) / (execution_id + ".json")).read_text(encoding="utf-8")
        )
        if result["stop_reason"] in {"dispatching", "running", "cancel_requested"}:
            result["recovery_status"] = (
                "interrupted_or_uncertain; never automatically replay"
            )
        return result
