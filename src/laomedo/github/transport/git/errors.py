"""Error types for github / transport / git."""

from __future__ import annotations


class PushOutcomeUnknown(RuntimeError):
    """A nonzero Git exit; its remote effect remains unknown regardless of hint."""

    def __init__(self, category: str, exit_code: int | None):
        self.code = "push_outcome_unknown"
        super().__init__(self.code)
        self.category = category
        self.exit_code = exit_code

    def __reduce__(self):
        """Reconstruct with the transport evidence, not the public code argument."""
        return type(self), (self.category, self.exit_code)
