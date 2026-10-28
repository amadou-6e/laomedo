"""Error types for agents / workspace."""

from __future__ import annotations


class GitWorkspaceError(RuntimeError):
    """An opt-in Git checkout failed closed before agent dispatch."""
