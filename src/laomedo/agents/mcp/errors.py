"""Safe failures at the external MCP admission and invocation boundary."""

from laomedo.agents.errors import RunnerError


class McpError(RunnerError):
    """Reject external access without exposing native errors or upstream credentials.

    ``code`` is a stable machine category. An invocation failure never establishes
    that the remote operation had no effect and never authorizes automatic replay.
    """

    def __init__(self, code: str):
        """Store only a machine category; callers must not supply upstream text."""
        self.code = code
        super().__init__(code)
