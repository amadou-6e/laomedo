"""Error types for host / credentials / claude."""

from __future__ import annotations


class LocalClaudeLoginError(RuntimeError):
    """Host login validation or local access-only credential mirroring failed.

    ``code`` is a closed public category; credentials, refresh material and
    raw host authentication errors must never be supplied as its value."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
