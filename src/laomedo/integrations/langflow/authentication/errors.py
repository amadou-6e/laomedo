"""Private browser lease persistence failures."""


class PrivateSessionError(RuntimeError):
    """Lease admission or persistence failed; private access must stay locked.

    Missing, expired and revoked cookies resolve to no lease rather than this
    exception. No credential or database diagnostic is exposed in its arguments.
    """

    code = "private_session_unavailable"

    def __init__(self):
        super().__init__(self.code)
