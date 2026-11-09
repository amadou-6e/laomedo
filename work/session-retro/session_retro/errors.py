"""Stable local failures never imply remote execution or automatic recovery."""

from session_retro.settings import ERROR_MESSAGES


class RetrospectiveError(ValueError):
    """Reject invalid evidence or unsafe source changes; original files stay untouched."""

    def __init__(self, code: str):
        """Retain the stable failure category without logging native payloads."""
        self.code = code
        super().__init__(code)

    @property
    def explanation(self) -> str:
        """Describe the known failure without including native payloads.

        Returns
        -------
        str
            Safe catalogue explanation, with a descriptive unknown-code fallback.
        """
        return ERROR_MESSAGES.get(
            self.code, ERROR_MESSAGES["filesystem_or_settings_failed"]
        )
