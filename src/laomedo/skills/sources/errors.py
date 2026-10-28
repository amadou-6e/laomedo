"""Error types for skills / sources."""

from __future__ import annotations


class SourceError(ValueError):
    """Skill source discovery or resolution was refused.

    ``code`` must be an existing nonsecret category accepted by the service
    boundary, never a repository credential or raw upstream response."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
