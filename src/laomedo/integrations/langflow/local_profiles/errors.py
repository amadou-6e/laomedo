"""Profile failures with safe codes, never credential-bearing input or traces."""


class ProfileError(ValueError):
    """A profile boundary could not complete; no authentication is implied.

    `code` is stable and safe for the shared catalogue. Creation failures can be
    unconfirmed, so callers must reconcile persisted state instead of replaying.
    Exception arguments contain only the code, never submitted fields.
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
