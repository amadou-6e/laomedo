"""Host-derived Activity identity and native page reads for an isolated graph."""

from functools import partial

from laomedo.agents.activity.capture import ActivityCapture
from laomedo.agents.activity.models import ActivityInvocation, CaptureIdentity
from laomedo.agents.activity.store import ActivityStore


class ProviderGraphActivity:
    """Reuse the common observer; graph processes never see its store or reader."""

    def __init__(self, database, controllers, plan, job_id):
        self.store = ActivityStore(database)
        self.controllers, self.plan, self.job_id = controllers, plan, job_id
        self.captures = {}

    def reserve(self, node):
        """Reserve the host's exact invocation before admitting a native start."""
        if node.vertex_id in self.captures:
            raise ValueError("activity_attempt_already_exists")
        identity = CaptureIdentity.from_values(
            str(self.plan.profile_id),
            str(self.plan.flow_id),
            node.vertex_id,
            provider={
                "codex": "codex-cli",
                "claude": "claude-code",
                "opencode": "opencode",
            }[node.provider],
            execution=str(self.job_id),
        )
        invocation = ActivityInvocation(
            store=self.store, invocation_id=self.store.start(identity)
        )
        self.captures[node.vertex_id] = ActivityCapture(
            invocation=invocation,
            native_feed=partial(
                self.controllers.read_graph_activity, self.plan.profile_id, node
            ),
            timeout=node.policy.timeout_seconds,
        )

    def observe(self, vertex_id, record):
        """Bind only a controller acknowledgement and its native initial attempt."""
        capture = self.captures.get(vertex_id)
        if capture is None:
            return
        capture.bind(record["run_id"], record.get("activity_initial_attempt_id"))
        if record.get("status") in {"completed", "failed", "cancelled", "timeout"}:
            capture.dispatched(result=record)

    def interrupted(self, vertex_id):
        """Seal unbound observation without inferring whether native work occurred."""
        capture = self.captures.get(vertex_id)
        if capture is not None:
            capture.dispatched()
