"""Error types for skills / inspection."""

from __future__ import annotations


class InspectionError(ValueError):
    """A skill tree failed bounded, non-executing filesystem inspection.

    ``code`` identifies the unsafe path, unsupported entry or resource limit;
    no inspected file content is included in the error contract."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
