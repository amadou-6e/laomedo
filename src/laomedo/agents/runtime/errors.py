"""Error types for agents / runtime."""

from __future__ import annotations


class RunnerError(ValueError):
    """Runner validation, isolation, native execution or reconciliation failed.

    ``code`` retains the boundary category. Consult the durable run record
    before deciding whether dispatch occurred or retry is safe."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
