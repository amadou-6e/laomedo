"""Error types for host / credentials / siwc."""

from __future__ import annotations


class AuthError(ValueError):
    """Subscription authentication or token validation was refused.

    ``code`` is the existing safe category, never a token, claim payload or
    raw identity-provider response. Refresh or recovery remains host-owned."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
