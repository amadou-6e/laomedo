"""Internal Git failure observations; callers retain their public error categories."""

from subprocess import TimeoutExpired


class GitOperationError(ValueError):
    """A named Git operation failed before returning its admitted resource.

    The stable code is safe to translate at the owning application boundary.
    Native output and credentials are deliberately not part of this exception.
    """

    def __init__(self, code: str):
        """Retain the existing machine category and ValueError argument shape."""
        self.code = code
        super().__init__(code)


class GitCommandTimeout(TimeoutExpired):
    """A command exceeded its deadline; cleanup and effect outcome are distinct.

    ``cleanup_verified`` reports process-tree cleanup only. It does not establish
    whether a push/fetch completed remotely and must never authorize a blind retry.
    """

    def __init__(self, arguments: list[str], timeout: float, cleanup_verified: bool):
        """Preserve TimeoutExpired compatibility without retaining an environment."""
        super().__init__(arguments, timeout)
        self.cleanup_verified = cleanup_verified
        self.code = (
            "git_timeout" if cleanup_verified else "git_timeout_cleanup_unverified"
        )

    def __str__(self) -> str:
        """Describe the deadline without rendering command arguments or paths."""
        cleanup = "confirmed" if self.cleanup_verified else "not confirmed"
        return (
            f"A local Git command exceeded its deadline; process cleanup was {cleanup}."
        )

    def __reduce__(self):
        """Retain cleanup observation when an exception crosses a process boundary."""
        return type(self), (self.cmd, self.timeout, self.cleanup_verified)


class GitCommandLimitExceeded(GitOperationError):
    """An active read budget was exceeded; the runner confirms cleanup before export."""

    def __init__(self):
        super().__init__("git_command_limit_exceeded")
        self.cleanup_verified = False


class GitCommandCleanupError(GitOperationError):
    """Owned process-tree termination could not be confirmed; never authorize a retry."""

    def __init__(self):
        super().__init__("git_command_cleanup_unverified")
        self.cleanup_verified = False
