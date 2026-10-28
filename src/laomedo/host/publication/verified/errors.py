"""Error types for host / publication / verified."""

from __future__ import annotations


class VerifiedGitStageError(RuntimeError):
    """Local Git staging or classification failed before provider contact.

    ``code`` preserves the refusal category; no external write is implied."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class VerifiedStageError(RuntimeError):
    """Stage verification refused publication before consulting credentials.

    ``code`` preserves the failed integrity or policy category; the result
    must not be used as authorization for an external operation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
