"""Error types for agents / artifacts."""

from __future__ import annotations


class ArtifactError(ValueError):
    """Artifact selection, path safety or snapshot integrity was refused.

    ``code`` is the existing machine category, not a filename or file content.
    No successful artifact materialization may be inferred from this exception."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
