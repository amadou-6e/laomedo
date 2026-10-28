"""Error types for host / publication / verified."""

from __future__ import annotations


class VerifiedGitStageError(RuntimeError):
    """Local Git staging or classification failed before provider contact."""


class VerifiedStageError(RuntimeError):
    """Refusal before provider credentials or a Git transport are consulted."""
