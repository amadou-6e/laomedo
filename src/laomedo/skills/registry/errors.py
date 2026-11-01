"""Error types for skills / registry."""

from __future__ import annotations


class SkillStoreError(ValueError):
    """A skill registry validation, integrity or lifecycle operation failed.

    ``code`` is the stable machine category consumed by service boundaries.
    This base includes invalid input and failed invariants; it does not imply
    that a conflict can be repaired by replaying a write."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ConflictError(SkillStoreError):
    """A registry write conflicts with its expected revision or exclusive owner.

    Inherits the code-bearing SkillStoreError constructor and ValueError handling.
    No write is authorized by catching this exception: inspect current registry
    state and the specific code (revision mismatch, busy or interrupted transition)
    before choosing recovery. A blind replay may overwrite another revision.
    """
