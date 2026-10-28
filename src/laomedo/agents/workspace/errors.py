"""Error types for agents / workspace."""

from __future__ import annotations


class GitWorkspaceError(RuntimeError):
    """An opt-in Git workspace check failed closed before agent dispatch.

    ``code`` identifies the failed checkout or binding check; no successful
    workspace preparation or permission to dispatch is implied."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
