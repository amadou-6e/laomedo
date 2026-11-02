"""Route admitted Git and REST operations through one selected repository identity."""

from laomedo.github.transport.git.transport import GitHubGitTransport


class GitHubMediatedTransport:
    """Route Git pushes and supported REST calls through one selected identity."""

    def __init__(self, git_transport: GitHubGitTransport, rest_transport):
        """Bind two existing transports only when their selected repositories match."""
        if git_transport.repository != rest_transport.repository:
            raise ValueError("repository_mismatch")
        self.git = git_transport
        self.rest = rest_transport

    def __call__(self, repository: str, operation: str, payload: dict, **binding):
        """Forward an admitted operation and its exact binding to Git or REST."""
        target = self.git if operation in {"git_push", "git_fetch"} else self.rest
        return target(repository, operation, payload, **binding)
