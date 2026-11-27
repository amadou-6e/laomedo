"""Host-owned admission for isolated graph workers; never a graph-side singleton."""

import hashlib
import math
import secrets
import time
from uuid import UUID, uuid4

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import GraphRunPlan
from laomedo.agents.connections.models import GraphRunReview
from laomedo.agents.connections.models import GraphNodeStart
from laomedo.agents.connections.models import GraphRunShutdown
from laomedo.agents.connections.settings import MAX_ACTIVE_PROVIDER_GRAPHS


class ProviderGraphRuns:
    """Bind worker authority and acknowledged source runs to one approved graph.

    This object must live outside the untrusted execution process. Knowing a
    flow, vertex, profile or native run ID never authenticates a worker.
    """

    def __init__(self, service, *, read_run):
        """Use the connection owner's lifecycle lock for all admission changes."""
        self.service = service
        self.read_run = read_run
        self._plans = {}
        self._runs = {}
        self._started = {}
        self._retired = {}

    @staticmethod
    def _key(capability):
        """Hash only well-formed opaque worker capabilities without logging them."""
        if (
            not isinstance(capability, str)
            or len(capability) != 64
            or any(character not in "0123456789abcdef" for character in capability)
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        return hashlib.sha256(capability.encode("ascii")).hexdigest()

    def _current(self, key, digest):
        """Resolve a live plan while holding the connection lifecycle lock."""
        plan = self._plans.get(key)
        if plan is not None and plan.deadline <= time.monotonic():
            self._retire(key)
            plan = None
        if plan is None:
            raise ProviderConnectionError("verified_review_unavailable")
        if not isinstance(digest, str) or not secrets.compare_digest(
            plan.graph_digest.encode("utf-8"), digest.encode("utf-8")
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        self.service.check_lease(plan.lease_hash)
        return plan

    def _node(self, plan, vertex_id):
        """Revalidate this vertex's admitted account without account fallback."""
        node = next((item for item in plan.nodes if item.vertex_id == vertex_id), None)
        if node is None:
            raise ProviderConnectionError("verified_review_unavailable")
        record = self.service.admitted(
            plan.profile_id, node.connection_id, node.generation
        )
        if record.provider != node.provider:
            raise ProviderConnectionError("verified_review_unavailable")
        return node

    def admit(self, plan: GraphRunPlan):
        """Issue one capability from a host-approved plan, never a worker claim."""
        if not isinstance(plan, GraphRunPlan):
            raise ProviderConnectionError("verified_review_unavailable")
        with self.service._lock:
            now = time.monotonic()
            for key, previous in tuple(self._plans.items()):
                if previous.deadline <= now:
                    self._retire(key)
            if (
                not math.isfinite(plan.deadline)
                or plan.deadline <= now
                or len(self._plans) >= MAX_ACTIVE_PROVIDER_GRAPHS
                or len({node.vertex_id for node in plan.nodes}) != len(plan.nodes)
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            self.service.check_lease(plan.lease_hash)
            for node in plan.nodes:
                self._node(plan, node.vertex_id)
                if node.review_source is not None:
                    source = self._node(plan, node.review_source)
                    if (
                        node.provider != "claude"
                        or source.vertex_id == node.vertex_id
                        or source.review_source is not None
                    ):
                        raise ProviderConnectionError("verified_review_unavailable")
            capability = secrets.token_hex(32)
            key = self._key(capability)
            self._plans[key] = plan
            self._runs[key] = {}
            self._started[key] = {}
            return capability

    def resolve(self, capability, graph_digest, vertex_id):
        """Authorize only one exact graph vertex under its current account epoch."""
        with self.service._lock:
            plan = self._current(self._key(capability), graph_digest)
            return self._node(plan, vertex_id)

    def plan(self, capability, graph_digest):
        """Resolve host composition state; this is not a worker request operation."""
        with self.service._lock:
            return self._current(self._key(capability), graph_digest)

    def run_for_vertex(self, capability, graph_digest, vertex_id):
        """Resolve only this vertex's host-acknowledged native run."""
        with self.service._lock:
            key = self._key(capability)
            plan = self._current(key, graph_digest)
            self._node(plan, vertex_id)
            run_id = self._runs[key].get(vertex_id)
            if run_id is None:
                raise ProviderConnectionError("verified_review_unavailable")
            return run_id

    def bind_run(self, capability, graph_digest, vertex_id, run_id):
        """Record a host-observed acknowledgement once; never accept worker output."""
        with self.service._lock:
            self._bind_run(self._key(capability), graph_digest, vertex_id, run_id)

    def _bind_run(self, key, graph_digest, vertex_id, run_id):
        """Bind only the runner record with this vertex's host-issued request ID."""
        try:
            if not isinstance(run_id, str) or str(UUID(run_id)) != run_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ProviderConnectionError("verified_review_unavailable") from None
        with self.service._lock:
            plan = self._current(key, graph_digest)
            self._node(plan, vertex_id)
            runs = self._runs[key]
            if (
                vertex_id not in self._started[key]
                or vertex_id in runs
                or run_id in runs.values()
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            record = self.read_run(plan.profile_id, self._node(plan, vertex_id), run_id)
            if (
                not isinstance(record, dict)
                or record.get("run_id") != run_id
                or record.get("client_request_id") != self._started[key][vertex_id]
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            runs[vertex_id] = run_id

    def bind_review_run(self, review: GraphRunReview, run_id):
        """Bind a review's native acknowledgement before releasing its start gate."""
        with self.service._lock:
            self.check_review(review)
            self._bind_run(
                review.worker_key, review.graph_digest, review.target.vertex_id, run_id
            )

    def begin_node(self, capability, graph_digest, vertex_id):
        """Reserve one native start per approved vertex before crossing dispatch."""
        with self.service._lock:
            key = self._key(capability)
            plan = self._current(key, graph_digest)
            node = self._node(plan, vertex_id)
            if vertex_id in self._started[key]:
                raise ProviderConnectionError("verified_review_unavailable")
            if node.review_source is not None:
                self._review(key, graph_digest, vertex_id)
            request_id = str(uuid4())
            self._started[key][vertex_id] = request_id
            return GraphNodeStart(node=node, request_id=request_id)

    def _review(self, key, graph_digest, vertex_id):
        """Project an exact review while the caller holds the lifecycle lock."""
        plan = self._current(key, graph_digest)
        node = self._node(plan, vertex_id)
        if node.provider != "claude" or node.review_source is None:
            raise ProviderConnectionError("verified_review_unavailable")
        source = self._node(plan, node.review_source)
        run_id = self._runs[key].get(node.review_source)
        if run_id is None:
            raise ProviderConnectionError("verified_review_unavailable")
        return GraphRunReview(
            profile_id=plan.profile_id,
            lease_hash=plan.lease_hash,
            worker_key=key,
            graph_digest=plan.graph_digest,
            source=source,
            target=node,
            source_run=run_id,
        )

    def review(self, capability, graph_digest, vertex_id):
        """Derive review authority from this invocation, never worker selectors."""
        with self.service._lock:
            return self._review(self._key(capability), graph_digest, vertex_id)

    def check_review(self, review: GraphRunReview):
        """Recheck a staged review before any native dispatch can reserve work."""
        with self.service._lock:
            if (
                self._review(
                    review.worker_key, review.graph_digest, review.target.vertex_id
                )
                != review
                or review.target.vertex_id not in self._started[review.worker_key]
            ):
                raise ProviderConnectionError("verified_review_unavailable")

    def check_review_dispatch(self, review: GraphRunReview):
        """Refuse native execution until the host acknowledged this target run."""
        with self.service._lock:
            self.check_review(review)
            if review.target.vertex_id not in self._runs[review.worker_key]:
                raise ProviderConnectionError("verified_review_unavailable")

    def check_node_dispatch(self, capability, graph_digest, vertex_id):
        """Require a live host acknowledgement before source-node model work."""
        self.run_for_vertex(capability, graph_digest, vertex_id)

    def finish(self, capability):
        """Revoke first, returning host receipts for exact native cancellation."""
        with self.service._lock:
            key = self._key(capability)
            self._retire(key)
            return self._retired.get(key)

    def _retire(self, key):
        """Separate revoked cleanup receipts from the live admission capacity."""
        plan = self._plans.pop(key, None)
        self._runs.pop(key, None)
        started = self._started.pop(key, {})
        if plan is not None:
            self._retired[key] = GraphRunShutdown(
                profile_id=plan.profile_id,
                starts=tuple(
                    GraphNodeStart(node=node, request_id=started[node.vertex_id])
                    for node in plan.nodes
                    if node.vertex_id in started
                ),
            )

    def settle(self, capability):
        """Forget only a revoked receipt after its supervisor confirms cleanup."""
        with self.service._lock:
            self._retired.pop(self._key(capability), None)

    def close(self):
        """Revoke all worker authority during host shutdown, without dispatch."""
        with self.service._lock:
            self._plans.clear()
            self._runs.clear()
            self._started.clear()
            self._retired.clear()
