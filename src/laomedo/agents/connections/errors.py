"""Safe failures of saved-connection ownership and lifecycle admission."""


class ProviderConnectionError(ValueError):
    """Reject an operation without exposing credentials or changing another owner.

    `code` is the stable boundary category; user-facing recovery belongs to the
    shared error catalogue. Failed login admission never replaces saved secrets.
    """

    def __init__(self, code: str):
        """Retain a fixed machine category as the exception argument and code."""
        self.code = code
        super().__init__(code)
