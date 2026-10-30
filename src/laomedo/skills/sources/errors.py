"""Error types for skills / sources."""

from __future__ import annotations


class SourceError(ValueError):
    """Skill source discovery or resolution was refused.

    ``code`` must be an existing nonsecret category accepted by the service
    boundary, never a repository credential or raw upstream response.
    ``repository_cleanup_unverified`` specifically preserves uncertainty about
    local Git descendants. It does not establish termination, permit removing
    owned staging or authorize an immediate repeat of the source operation.
    Other existing categories retain their previous outcome guarantees.
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
