"""Exact Claude turn session lifetime over provider policy and py-docker."""

from contextlib import ExitStack
import sys
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.base.interim import BaseAgentRuntime
from laomedo.agents.agents.base.models.runtime import (
    RuntimeObservation,
    CancellationObservation,
    CleanupObservation,
)


class ClaudeAgentRuntime(BaseAgentRuntime):
    """Own one turn's native session and creator-thread cleanup context."""

    def __init__(self, policy, spec, receipt, seconds, *, cancelled=None):
        """Open exactly the existing bounded native session; no ACP/model request."""
        self._stack = ExitStack()
        self._closed = False
        self._cleanup_confirmed = None
        self._cancelled = cancelled
        try:
            self.session = self._stack.enter_context(
                policy._session_context(spec, receipt, seconds)
            )
        except BaseException:
            self._stack.__exit__(*sys.exc_info())
            raise

    def __enter__(self):
        """Expose the owned session only to the existing composed ACP adapter."""
        return self.session

    def __exit__(self, kind, error, traceback):
        """Pass the original exception through the exact native cleanup contexts."""
        try:
            result = self._stack.__exit__(kind, error, traceback)
        except BaseException:
            self._cleanup_confirmed = None
            raise
        else:
            self._cleanup_confirmed = True
            return result
        finally:
            self._closed = True

    def observe(self) -> RuntimeObservation:
        """A launched native turn is not evidence that its ACP handshake is ready."""
        return RuntimeObservation(
            provider="claude",
            launched=not self._closed,
            ready=None,
            native_session=None,
        )

    def request_cancel(self) -> CancellationObservation:
        """Signal the existing prompt flag without claiming native interruption."""
        flag = self._cancelled if not self._closed else None
        if flag is not None:
            flag.set()
        return CancellationObservation(requested=flag is not None, confirmed=None)

    async def shutdown(self) -> CleanupObservation:
        """Close the exact turn context or propagate native cleanup uncertainty."""
        if self._closed and self._cleanup_confirmed is not True:
            raise RunnerError("container_termination_unverified")
        if not self._closed:
            try:
                self._stack.close()
            except BaseException:
                self._closed = True
                self._cleanup_confirmed = None
                raise
            self._closed = True
            self._cleanup_confirmed = True
        return CleanupObservation(confirmed=True, scope="claude_turn_session")
