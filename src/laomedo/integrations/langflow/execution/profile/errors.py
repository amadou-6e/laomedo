"""Fixed per-profile native API runtime failure without private diagnostics."""

from laomedo.integrations.langflow.execution.errors import GraphRuntimeError


class NativeProfileError(GraphRuntimeError):
    """A profile's operational container could not be started, verified or kept.

    The profile's persisted operational volume is never deleted on this error,
    and no broker or GitHub authority is implied or revoked by it. Recovery is
    an explicit new `acquire` after the failed instance has been removed.
    """

    code = "graph_profile_runtime_unavailable"
