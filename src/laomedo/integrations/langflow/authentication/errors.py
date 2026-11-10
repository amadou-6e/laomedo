"""Private browser lease persistence failures."""


class PrivateSessionError(RuntimeError):
    """Lease admission or persistence failed; private access must stay locked.

    Missing, expired and revoked cookies resolve to no lease rather than this
    exception. No credential or database diagnostic is exposed in its arguments.
    """

    code = "private_session_unavailable"

    def __init__(self):
        super().__init__(self.code)


class PrivateSessionRequired(PrivateSessionError):
    """Private admission lacks a matching live explicit-login lease.

    This does not disconnect a GitHub account or establish upstream logout.
    The boundary uses a dedicated recovery response rather than an automatic
    upstream authentication refresh loop. Storage failure remains a separate code.
    """

    code = "private_session_required"
