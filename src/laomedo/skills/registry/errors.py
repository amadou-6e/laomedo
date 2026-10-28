"""Error types for skills / registry."""

from __future__ import annotations


class SkillStoreError(ValueError):
    pass


class ConflictError(SkillStoreError):
    pass
