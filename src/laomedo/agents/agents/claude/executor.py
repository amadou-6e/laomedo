"""Claude-native workspace execution; HTTP adaptation and credentials are separate."""

import secrets
import threading
import time
from uuid import uuid4
from laomedo.agents.agents.base.base import BaseInterruptibleCommandExecutor
from laomedo.agents.agents.base.models import (
    CommandRequest,
    CommandResult,
    CleanupObservation,
    CancellationObservation,
)
from laomedo.agents.agents.claude.http.commands import ClaudeCommandTransport
from laomedo.agents.errors import RunnerError


class ClaudeCommandExecutor(BaseInterruptibleCommandExecutor):
    """One run capability; all commands execute without the Claude profile/network."""

    def __init__(self, runtime, root, record, cancelled, deadline, *, mediation=None):
        """Bind admitted configuration and owned state; provider startup errors propagate before use."""
        self.runtime, self.root, self.record = runtime, root, record
        self.cancelled, self.deadline = cancelled, deadline
        self.mediation = mediation
        self.lock = threading.Lock()
        self.cleanup_failed = False
        self.error_code = None
        self.stopping = threading.Event()
        self.closed = False

        self.transport = ClaudeCommandTransport(self)

    def shutdown(self) -> CleanupObservation:
        """Stop admission, close owned resources and return exact cleanup evidence."""
        self.request_cancel()
        self.transport.close()
        return CleanupObservation(
            confirmed=True, scope="claude_command_workers_and_transport"
        )

    def request_cancel(self) -> CancellationObservation:
        """Signal the owned job without blocking on cleanup or claiming native ack."""
        self.closed = True
        self.stopping.set()
        idle = self.lock.acquire(blocking=False)
        if idle:
            self.lock.release()
        return CancellationObservation(requested=not idle, confirmed=None)

    def execute(self, request: CommandRequest) -> CommandResult:
        """Run one admitted command; keep its combined-output native wire semantics."""
        if request.command is None or request.argv is not None:
            raise RunnerError("claude_workspace_command_invalid")
        result = self._execute_native(
            {"command": request.command}, deadline=request.deadline
        )
        return CommandResult(
            exit_code=result["exit_code"],
            stdout=result["output"],
            cleanup=CleanupObservation(
                confirmed=True, scope="claude_command_worker_and_lease"
            ),
        )

    def _execute_native(self, value, *, deadline=None):
        """Run one bounded native command under the selected worker policy; uncertain cleanup propagates as a stable failure."""
        deadline = (
            min(self.deadline, deadline) if deadline is not None else self.deadline
        )
        if (
            not isinstance(value, dict)
            or set(value) != {"command"}
            or not isinstance(value["command"], str)
        ):
            raise RunnerError("claude_workspace_command_invalid")
        if not value["command"].strip() or len(value["command"]) > 60000:
            raise RunnerError("claude_workspace_command_invalid")
        with self.lock:
            if self.closed or self.cancelled.is_set():
                raise RunnerError("claude_cancelled")
            if time.monotonic() >= deadline:
                raise RunnerError("claude_turn_timeout")
            name, token = "laomedo-claude-command-" + uuid4().hex, uuid4().hex
            lease = self.runtime.lease(
                self.record["run_id"], name, token, self.cancelled
            )
            cleanup_confirmed = job_started = False
            try:
                worker_deadline = min(deadline, time.monotonic() + 120)
                spec = self.runtime.spec(
                    self.runtime.guarded(
                        ["sh", "-c", value["command"]], worker_deadline
                    ),
                    name=name,
                    run_id=self.record["run_id"],
                    token=token,
                    workspace=self.root.joinpath("workspace"),
                    worker=True,
                )
                job_started = True
                result = self.runtime.job(
                    spec,
                    timeout=max(1, worker_deadline - time.monotonic()),
                    cancelled=self.stopping,
                )
                cleanup_confirmed = True
                return {
                    "exit_code": result.exit_code,
                    "output": (result.stdout + result.stderr)[: 1024 * 1024].decode(
                        "utf-8", errors="replace"
                    ),
                }
            except RunnerError as error:
                if str(error) == "workspace_command_output_too_large":
                    self.error_code = "workspace_command_output_too_large"
                cleanup_confirmed = (
                    not job_started or str(error) != "container_termination_unverified"
                )
                raise
            finally:
                verified = cleanup_confirmed
                if verified:
                    try:
                        lease.finish()
                    except RuntimeError:
                        verified = False
                else:
                    lease.stop_heartbeats()
                if not verified:
                    self.cleanup_failed = True
                    self.cancelled.set()
                    raise RunnerError("container_termination_unverified")
