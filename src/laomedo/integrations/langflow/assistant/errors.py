"""Safe assistant refusals; messages never contain credentials or native payloads."""


class AssistantError(RuntimeError):
    """Refuse a named operation without claiming absence of uncertain remote effects."""

    def __init__(self, code: str, status: int = 409):
        """Retain only the stable machine category and intended HTTP status."""
        self.code = code
        self.status = status
        super().__init__(code)
