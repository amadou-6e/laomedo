"""Error types for github / issues."""

from __future__ import annotations


class IssueContextError(ValueError):
    """A typed failure that must not become an empty issue or PR list."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
