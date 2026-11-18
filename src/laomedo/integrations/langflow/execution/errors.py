"""Isolated-runtime failures shared by the worker and profile supervisors."""


class GraphRuntimeError(RuntimeError):
    """A local isolated runtime could not be controlled, verified or trusted.

    Raised by shared Docker control (`BaseDockerRuntime`) through each runtime's
    `runtime_error` subclass, so callers see the worker or profile contract.
    The message is only the stable machine code, never Docker output, graph
    content or capabilities.
    """

    code = "graph_runtime_unavailable"

    def __init__(self):
        """Expose only the stable machine code."""
        super().__init__(self.code)

    def __reduce__(self):
        """Preserve the fixed no-argument outcome across serialization."""
        return type(self), ()
