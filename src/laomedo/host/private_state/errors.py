"""Internal fixed policy failures translated by each feature boundary."""


class PrivateStateError(RuntimeError):
    """Private directory admission or permissions could not be established.

    Only trusted fixed policy codes belong here. Callers must translate this
    internal failure; it never carries a path, SID or native diagnostic text.
    """

    def __init__(self, code: str) -> None:
        """Retain a fixed internal reason without native response data."""
        self.code = code
        super().__init__(code)
