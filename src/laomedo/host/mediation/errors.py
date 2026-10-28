"""Error types for host / mediation."""

from __future__ import annotations


class MediationError(Exception):
    """Typed refusal; `code` is safe for a stage or trace."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class KnownRejected(Exception):
    """Transport-confirmed rejection which did not create a remote effect."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
