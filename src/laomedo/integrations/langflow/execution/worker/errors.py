"""Fixed single-job worker failure without private diagnostics in its message."""

from laomedo.integrations.langflow.execution.errors import GraphRuntimeError


class GraphWorkerError(GraphRuntimeError):
    """Execution or private-channel uncertainty prevents further job dispatch.

    This error never implies that an already dispatched external write failed;
    the broker's durable effect outcome remains authoritative. Callers must not
    replay a write merely because the worker process or pipe was lost.
    """

    code = "github_graph_runtime_unavailable"
