"""Host-only provider and anonymous-Issue dispatch behind one isolated job pipe."""

import threading
from uuid import UUID

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.errors import RunnerError
from laomedo.agents.interface.models import PrecheckEvidence, RunnerDiagnostics
from laomedo.github.transport.rest.public import PublicGitHubIssueTransport
from laomedo.integrations.langflow.execution.providers.models import ProviderWorkerReply
from laomedo.integrations.langflow.execution.providers.settings import (
    PROVIDER_STATUS_FIELDS,
)


class ProviderGraphDispatcher:
    """Derive authority from host admission, never pipe-supplied account selectors."""

    def __init__(
        self,
        controllers,
        capability,
        graph_digest,
        issues=(),
        *,
        gateway=None,
        activity=None,
    ):
        self.controllers = controllers
        self.capability = capability
        self.graph_digest = graph_digest
        self.plan = controllers.graph_runs.plan(capability, graph_digest)
        self.issues = {item.vertex_id: item for item in issues}
        if len(self.issues) != len(issues) or (
            gateway is not None
            and any(
                type(transport) is not PublicGitHubIssueTransport
                for transport in gateway.transports.values()
            )
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        self.gateway = gateway
        self.activity = activity
        self.aliases = {}
        self.staged = {}
        self.node_outcomes = {}

    def observe_node(self, vertex_id, record):
        """Retain terminal build evidence from native records, never worker claims."""
        if record.get("status") in {"completed", "failed"}:
            self.node_outcomes[vertex_id] = {
                "node_id": vertex_id,
                "state": "succeeded" if record["status"] == "completed" else "failed",
            }

    def _status(self, vertex_id, record):
        """Release graph evidence only, without native tasks, paths or host request IDs."""
        self.observe_node(vertex_id, record)
        if self.activity is not None:
            self.activity.observe(vertex_id, record)
        result = {
            key: value for key, value in record.items() if key in PROVIDER_STATUS_FIELDS
        }
        result["client_request_id"] = self.aliases.get(vertex_id)
        result["precheck"] = PrecheckEvidence.from_result(
            record.get("precheck")
        ).model_dump()
        return result

    def _alias(self, body):
        """Accept an observational worker correlation UUID, never native authority."""
        try:
            alias = body["request_id"]
            if not isinstance(alias, str) or str(UUID(alias)) != alias:
                raise ValueError
            return alias
        except (TypeError, KeyError, ValueError, AttributeError):
            raise ProviderConnectionError("verified_review_unavailable") from None

    def _review(self, call):
        """Stage the host's actual patch and return only its semantic hash."""
        alias = self._alias(call.body)
        staged = self.controllers.stage_review_request(
            self.capability, self.graph_digest, call.vertex_id, call.body
        )
        self.aliases[call.vertex_id] = alias
        self.staged[call.vertex_id] = staged
        return {"expected_request_hash": staged.expected_request_hash}

    def _start(self, call, node):
        """Dispatch one approved native node without exposing its gateway or grant."""
        alias = self._alias(call.body)
        if node.review_source is None:
            record = self.controllers.start_graph_node(
                self.capability, self.graph_digest, call.vertex_id, call.body
            )
            self.aliases[call.vertex_id] = alias
            return self._status(call.vertex_id, record)
        staged = self.staged.pop(call.vertex_id, None)
        if (
            staged is None
            or alias != self.aliases.get(call.vertex_id)
            or node.policy is None
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        body = node.policy.native_request(call.body, staged.body["request_id"])
        if body != staged.body:
            raise ProviderConnectionError("verified_review_unavailable")
        slot = self.controllers.graph_native(self.plan.profile_id, node)
        with self.controllers.service._lock:
            self.controllers.admit_operation(slot)
            gate = threading.Event()
            try:
                with self.controllers.admit_verified_review(
                    staged.grant, slot, body
                ) as admission:
                    record = self.controllers.reserve_graph_review(
                        slot, admission, gate
                    )
                return self._status(call.vertex_id, record)
            finally:
                slot.operations -= 1
                gate.set()

    def _http(self, call):
        """Interpret only closed native operations on the requested vertex's own run."""
        node = self.controllers.graph_runs.resolve(
            self.capability, self.graph_digest, call.vertex_id
        )
        if call.path == "/v1/runs/async" and call.method == "POST":
            if self.activity is not None:
                self.activity.reserve(node)
            try:
                return 202, self._start(call, node)
            except Exception:
                if self.activity is not None:
                    self.activity.interrupted(call.vertex_id)
                raise
        run_id = self.controllers.graph_runs.run_for_vertex(
            self.capability, self.graph_digest, call.vertex_id
        )
        slot = self.controllers.graph_native(self.plan.profile_id, node)
        if call.method == "GET" and (
            call.path == "/v1/runs/" + run_id
            or call.path == "/v1/requests/" + str(self.aliases.get(call.vertex_id))
        ):
            return 200, self._status(call.vertex_id, slot.runner.status(run_id))
        if call.method == "POST" and call.path == "/v1/runs/" + run_id + "/cancel":
            if call.body is not None and set(call.body) - {"expected_request_hash"}:
                raise ProviderConnectionError("verified_review_unavailable")
            return 200, self._status(call.vertex_id, slot.runner.cancel(run_id))
        raise ProviderConnectionError("verified_review_unavailable")

    def _issue(self, call):
        """Read one approved public issue without any saved-account fallback."""
        selected = self.issues.get(call.vertex_id)
        body = call.body
        if (
            selected is None
            or self.gateway is None
            or not isinstance(body, dict)
            or set(body) != {"number", "labels", "state"}
            or body["number"] != selected.number
            or body["labels"] != list(selected.labels)
            or body["state"] != selected.state
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        return self.gateway.execute(
            selected.repository_url,
            list(selected.labels),
            selected.state,
            selected.number,
        )

    def request(self, call):
        """Handle one bounded pipe call and fence again before releasing its payload."""
        try:
            self.controllers.graph_runs.plan(self.capability, self.graph_digest)
            if call.action == "review":
                status, payload = 200, self._review(call)
            elif call.action == "issue":
                status, payload = 200, self._issue(call)
            else:
                status, payload = self._http(call)
            self.controllers.graph_runs.plan(self.capability, self.graph_digest)
            return ProviderWorkerReply(
                request_id=call.request_id, status=status, payload=payload
            )
        except (
            ProviderConnectionError,
            RunnerError,
            ValueError,
            KeyError,
            OSError,
        ) as error:
            code = (
                RunnerDiagnostics.safe_code(getattr(error, "code", None))
                or "provider_runner_unavailable"
            )
            return ProviderWorkerReply(
                request_id=call.request_id,
                status=409,
                payload={"status": "failed", "error_category": code},
            )
