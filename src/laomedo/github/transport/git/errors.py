"""Error types for github / transport / git."""

from __future__ import annotations


class PushOutcomeUnknown(RuntimeError):
    """A nonzero Git exit; its remote effect remains unknown regardless of hint."""

    def __init__(self, category: str, exit_code: int | None):
        super().__init__("push_outcome_unknown")
        self.category = category
        self.exit_code = exit_code
