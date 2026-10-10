"""Host-owned first-call reservation for a Langflow Codex stage.

The opt-in custom component can call this controller through the local join
HTTP service. It records the saved-flow revision separately from the
unverified executing editor graph and never replays an uncertain native start.
"""

from hashlib import sha256
import json
from threading import RLock
from uuid import UUID

from .workflow_run_store import LaunchError, WorkflowRunStore


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _uuid(value, category):
    try:
        canonical = str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise LaunchError(category) from None
    if canonical != value:
        raise LaunchError(category)
    return canonical


class LangflowJoinController:
    """Single-user local controller with a replaceable saved-flow resolver.

    The runner interface has start_async, lookup_request, status and cancel.
    A failed transport call is unknown even if it may never have reached the
    runner.
    """

    def __init__(self, store: WorkflowRunStore, runner, resolve_saved_flow):
        if not callable(resolve_saved_flow):
            raise ValueError("flow_resolver_required")
        self.store = store
        self.runner = runner
        self.resolve_saved_flow = resolve_saved_flow
        self._cancel_lock = RLock()

    def _reconcile_stop_after_failure(self, client_request_id):
        """Keep an earlier Stop active after an uncertain native response."""
        if not self.store.langflow_cancel_requested(client_request_id):
            return
        try:
            self.cancel(client_request_id)
        except Exception:
            # The original failed start remains unknown. A later status read
            # retries the exact lookup and cancellation under the saved intent.
            pass

    @staticmethod
    def _saved_graph(exported, flow_id, stage_id):
        if (not isinstance(exported, dict) or exported.get("id") != flow_id or
                not isinstance(exported.get("data"), dict)):
            raise LaunchError("saved_flow_identity_mismatch")
        graph = exported["data"]
        nodes = graph.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise LaunchError("unresolved_saved_graph")
        codes = {}
        for node in nodes:
            try:
                node_id = node["id"]
                code = node["data"]["node"]["template"]["code"]["value"]
            except (KeyError, TypeError):
                raise LaunchError("unresolved_component_identity") from None
            if (not isinstance(node_id, str) or not node_id or
                    not isinstance(code, str) or not code.strip() or node_id in codes):
                raise LaunchError("unresolved_component_identity")
            codes[node_id] = code
        if stage_id not in codes:
            raise LaunchError("stage_not_in_saved_flow")
        return graph, codes

    def _snapshot(self, client_id):
        row = self.store.langflow_client_snapshot(client_id)
        if row is None:
            return None
        return {"client_request_id": client_id, "run_id": row["run_id"],
                "trace_id": self.store.get(row["run_id"])["trace_id"],
                "invocation_id": row["invocation_id"],
                "runner_request_id": row["invocation_id"],
                "runner_run_id": row["runner_run_id"],
                "runner_request_hash": row["runner_request_hash"],
                "runner_provider": row["runner_provider"],
                "runner_raw_event_ref": row["runner_raw_event_ref"],
                "status": row["run_status"],
                "dispatch_attempts": row["dispatch_attempts"],
                "graph_basis": row["graph_basis"],
                "executing_graph_verified": False}

    def status(self, client_request_id):
        """Read native status; a pending Stop may reconcile and cancel exactly once."""
        client_request_id = _uuid(client_request_id, "invalid_client_request_id")
        snapshot = self._snapshot(client_request_id)
        if (snapshot is not None and snapshot["runner_run_id"] is None and
                snapshot["dispatch_attempts"] == 1 and
                self.store.langflow_cancel_requested(client_request_id)):
            return self.cancel(client_request_id)
        if snapshot is None or snapshot["runner_run_id"] is None:
            return snapshot
        try:
            native = self.runner.status(snapshot["runner_run_id"])
        except Exception as exc:
            raise LaunchError("runner_status_unknown") from exc
        if (not isinstance(native, dict) or
                native.get("run_id") != snapshot["runner_run_id"]):
            raise LaunchError("runner_status_identity_mismatch")
        if native.get("status") in {"completed", "cancelled", "failed",
                                    "timeout", "interrupted"}:
            self.store.record_runner_terminal(
                snapshot["run_id"], snapshot["invocation_id"],
                provider="codex", runner_run_id=snapshot["runner_run_id"],
                status=native["status"])
            snapshot = self._snapshot(client_request_id)
        return {**snapshot, "native_status": native.get("status"),
                "native_record": native,
                "cancel_requested": native.get("cancel_requested"),
                "cancel_confirmed": native.get("cancel_confirmed")}

    def start(self, *, client_request_id, flow_id, graph_run_id, stage_id,
              runner_body):
        """Persist a unique reservation before one native async start request."""
        client_request_id = _uuid(client_request_id, "invalid_client_request_id")
        if (not isinstance(flow_id, str) or not flow_id or
                not isinstance(stage_id, str) or not stage_id or
                graph_run_id is not None and
                (not isinstance(graph_run_id, str) or not graph_run_id) or
                not isinstance(runner_body, dict) or
                not isinstance(runner_body.get("task"), str) or
                not runner_body["task"].strip() or "request_id" in runner_body):
            raise LaunchError("invalid_langflow_start")
        body = dict(runner_body)
        client_hash = _digest({"flow_id": flow_id, "graph_run_id": graph_run_id,
                               "stage_id": stage_id, "runner_body": body})
        prior = self.store.langflow_client_snapshot(client_request_id)
        if prior is not None:
            if prior["client_request_hash"] != client_hash:
                raise LaunchError("client_request_identity_conflict")
            return self._snapshot(client_request_id)
        exported = self.resolve_saved_flow(flow_id)
        graph, codes = self._saved_graph(exported, flow_id, stage_id)
        run = self.store.reserve(graph=graph, component_code=codes,
                                 resolved_config=body,
                                 trigger={"kind": "langflow_playground",
                                          "flow_id": flow_id,
                                          "graph_run_id_reported": graph_run_id,
                                          "executing_graph_verified": False})
        run_id = run["run_id"]
        invocation_id = self.store.reserve_invocation(run_id, stage_id)
        request_hash = _digest(body)
        self.store.freeze_runner_request(run_id, invocation_id, request_hash)
        _, created = self.store.claim_langflow_client(
            client_request_id, client_hash, run_id=run_id,
            invocation_id=invocation_id, flow_id=flow_id,
            graph_run_id=graph_run_id, graph_basis="saved_flow_export")
        if not created:
            return self._snapshot(client_request_id)
        disposition = self.store.begin_langflow_client(client_request_id)
        if disposition != "dispatching":
            return self._snapshot(client_request_id)
        try:
            ack = self.runner.start_async({**body, "request_id": invocation_id})
        except Exception as exc:
            self.store.record_runner_failure(
                run_id, invocation_id, category="runner_transport_error")
            self._reconcile_stop_after_failure(client_request_id)
            raise LaunchError("runner_start_unknown") from exc
        if (not isinstance(ack, dict) or
                ack.get("client_request_id") != invocation_id or
                ack.get("request_hash") != request_hash or
                ack.get("provider") != "codex"):
            self.store.record_runner_failure(
                run_id, invocation_id, category="runner_ack_identity_mismatch")
            self._reconcile_stop_after_failure(client_request_id)
            raise LaunchError("runner_ack_identity_mismatch")
        try:
            self.store.bind_runner_ack(
                run_id, invocation_id, request_id=ack["client_request_id"],
                provider="codex", runner_run_id=ack.get("run_id"),
                raw_event_ref=ack.get("raw_event_ref"))
        except LaunchError:
            self.store.record_runner_failure(
                run_id, invocation_id, category="runner_binding_conflict")
            self._reconcile_stop_after_failure(client_request_id)
            raise
        if self.store.langflow_cancel_requested(client_request_id):
            self.cancel(client_request_id)
        return self._snapshot(client_request_id)

    def cancel(self, client_request_id):
        """Retain Stop before ack; reconcile only by read-only native lookup."""
        client_request_id = _uuid(client_request_id, "invalid_client_request_id")
        row = self.store.request_langflow_cancel(client_request_id)
        if row is None:
            return {"client_request_id": client_request_id, "status": "pending_start"}
        if row["dispatch_attempts"] == 0:
            self.store.begin_langflow_client(client_request_id)
            return self._snapshot(client_request_id)
        run_id, invocation_id = row["run_id"], row["invocation_id"]
        with self._cancel_lock:
            trace = self.store.trace_snapshot(run_id)
            if any(item["kind"] == "runner_cancel" for item in trace["receipts"]):
                return self._snapshot(client_request_id)
            runner_run_id = row["runner_run_id"]
            if runner_run_id is None:
                try:
                    found = self.runner.lookup_request(invocation_id)
                except Exception as exc:
                    if str(exc) == "request_not_found":
                        return {**self._snapshot(client_request_id),
                                "status": "cancel_pending_runner_lookup"}
                    raise LaunchError("runner_lookup_unknown") from exc
                if (not isinstance(found, dict) or
                        found.get("client_request_id") != invocation_id or
                        found.get("request_hash") != row["runner_request_hash"] or
                        found.get("provider") != "codex"):
                    raise LaunchError("runner_lookup_mismatch")
                self.store.bind_runner_ack(
                    run_id, invocation_id, request_id=invocation_id,
                    provider="codex", runner_run_id=found.get("run_id"),
                    raw_event_ref=found.get("raw_event_ref"))
                runner_run_id = found["run_id"]
            status = self.runner.status(runner_run_id)
            if status.get("status") in {"completed", "cancelled", "failed",
                                        "timeout", "interrupted"}:
                self.store.record_runner_observation(
                    run_id, invocation_id, provider="codex",
                    runner_run_id=runner_run_id, kind="runner_status",
                    payload={"status": status.get("status"),
                             "cancel_sent": False})
                return self.status(client_request_id)
            cancelled = self.runner.cancel(runner_run_id)
            self.store.record_runner_observation(
                run_id, invocation_id, provider="codex",
                runner_run_id=runner_run_id, kind="runner_cancel",
                payload={"cancel_requested": cancelled.get("cancel_requested"),
                         "cancel_confirmed": cancelled.get("cancel_confirmed")})
            return self.status(client_request_id)
