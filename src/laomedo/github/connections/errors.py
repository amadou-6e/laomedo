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


class GitHubConnectionError(RuntimeError):
    """Private connection persistence is unavailable or its outcome is unconfirmed.

    Callers must keep private access locked and preserve custody cleanup records.
    Database paths, provider diagnostics and credentials are never arguments.
    """

    code = "github_connection_unavailable"

    def __init__(self):
        """Expose only the fixed, safe connection outcome."""
        super().__init__(self.code)

    def __reduce__(self):
        """Preserve the fixed no-argument outcome across serialization."""
        return type(self), ()


class GitHubConnectionChanged(GitHubConnectionError):
    """An owner or generation check refused stale admission without changing it.

    A ready connection may still exist; this does not authorize another account,
    a replayed refresh, or automatic replacement of its current credential.
    """

    code = "github_connection_changed"


class GitHubRepositoryAccessError(GitHubConnectionError):
    """Current account or repository read access could not be confirmed online.

    A 404 does not establish repository existence or visibility. No stale cache,
    anonymous fallback, alternate credential or retry permission follows.
    """

    code = "github_repository_access_unconfirmed"


class GitHubReauthorizationRequired(GitHubConnectionError):
    """Credential absence, expiry or uncertain renewal prevents new private reads.

    The ready metadata is not replacement authority. A deliberate reconnect must
    verify the same account and explicit repository consent before committing.
    """

    code = "github_reauthorization_required"


class GitHubTokenUnsupported(GitHubConnectionError):
    """Deliberate token entry is outside the supported fine-grained format.

    No provider request, custody write or ready replacement is authorized.
    The token value and validation diagnostics never cross this boundary.
    """

    code = "github_token_unsupported"
