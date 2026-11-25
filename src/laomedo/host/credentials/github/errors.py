"""GitHub private-connection credential custody failures."""


class GitHubVaultError(RuntimeError):
    """Custody is unavailable or unconfirmed; no credential detail is exposed.

    A failed store may have written its exact provisional reference; a failed
    remove does not establish absence. The broker retains cleanup responsibility.
    This exception never establishes remote token revocation.
    """

    code = "github_credential_unavailable"

    def __init__(self):
        """Expose only the fixed custody outcome, never backend details."""
        super().__init__(self.code)

    def __reduce__(self):
        """Restore this safe no-argument exception without accepting arbitrary text."""
        return type(self), ()
