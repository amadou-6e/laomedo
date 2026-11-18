"""Saved-account graph-run refusals; no failure selects another account."""

from laomedo.github.connections.errors import GitHubConnectionError


class GitHubNodeAuthorizationError(GitHubConnectionError):
    """A graph's saved-account admission is missing, expired, stale or mismatched.

    No credential lookup or alternate account is authorized by this failure.
    Preparing a new run is required; a saved graph or job ID is never authority.
    """

    code = "github_node_authorization_unavailable"
