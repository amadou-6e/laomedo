"""Exact Claude turn session lifetime over provider policy and py-docker."""

from contextlib import ExitStack
import sys


class ClaudeAgentRuntime:
    """Own one turn's native session and creator-thread cleanup context."""

    def __init__(self, policy, spec, receipt, seconds):
        """Open exactly the existing bounded native session; no ACP/model request."""
        self._stack = ExitStack()
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
        return self._stack.__exit__(kind, error, traceback)
