"""Fixed native graph worker failure without private diagnostics in its message."""


class GraphWorkerError(RuntimeError):
    """Execution or private-channel uncertainty prevents further job dispatch.

    This error never implies that an already dispatched external write failed;
    the broker's durable effect outcome remains authoritative. Callers must not
    replay a write merely because the worker process or pipe was lost.
    """

    code = "github_graph_runtime_unavailable"

    def __init__(self):
        """Expose only the stable machine code, never graph content or capabilities."""
        super().__init__(self.code)
