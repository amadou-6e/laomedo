"""Safe OAuth protocol refusal without provider bodies, URLs or secret causes."""


class GitHubOAuthError(RuntimeError):
    """Refuse an incomplete exchange; no connection or permission is committed.

    An exchange may have reached GitHub. Its caller must consume the pending
    attempt or retain its durable refresh uncertainty marker rather than retry.
    """

    code = "github_oauth_unavailable"

    def __init__(self):
        """Expose only the stable machine code, with no underlying credential data."""
        super().__init__(self.code)

    def __reduce__(self):
        """Restore the fixed safe outcome without provider response arguments."""
        return type(self), ()
