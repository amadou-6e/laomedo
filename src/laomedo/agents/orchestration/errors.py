"""Error types for agents / handoffs."""

from __future__ import annotations


class HandoffError(ValueError):
    """A runner handoff failed validation, authorization or transport checks.

    ``code`` preserves the existing category; transport failure alone does not
    establish whether a previously dispatched remote operation finished."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
