"""Stable local failures never imply remote execution or automatic recovery."""


class RetrospectiveError(ValueError):
    """Reject invalid evidence or unsafe source changes; original files stay untouched."""

    def __init__(self, code: str):
        """Retain the stable failure category without logging native payloads."""
        self.code = code
        super().__init__(code)
