"""First-slice, single-invocation bridge from native runner to durable trace.

Langflow remains responsible for workflow scheduling. This bridge only reserves
and correlates one fresh native invocation; it never retries an uncertain POST.
"""

from .handoffs import HandoffError
from .workflow_run_store import LaunchError, runner_attempt_terminal


class RunnerTraceBridge:
    def __init__(self, store, adapter):
        self.store = store
        self.adapter = adapter

    def dispatch(self, run_id, stage_id, handoff, *, deadline, cancelled):
        if (handoff.get("operation") != "fresh" or
                handoff.get("target", {}).get("provider") != "codex"):
            raise LaunchError("first_slice_requires_fresh_codex")
        invocation_id = self.store.reserve_invocation(run_id, stage_id)
        _, request_hash = self.adapter.fresh_request(handoff, invocation_id)
        self.store.freeze_runner_request(run_id, invocation_id, request_hash)
        self.store.begin_invocation(run_id, invocation_id)
        def on_ack(ack):
            self.store.bind_runner_ack(
                run_id, invocation_id, request_id=ack["client_request_id"],
                provider="codex", runner_run_id=ack["run_id"],
                raw_event_ref=ack["raw_event_ref"])
        try:
            result = self.adapter.dispatch(
                handoff, deadline=deadline, cancelled=cancelled, early_start=True,
                runner_request_id=invocation_id, expected_request_hash=request_hash,
                on_ack=on_ack)
        except HandoffError as exc:
            if str(exc) == "runner_result_pending":
                self.store.record_runner_wait_uncertain(run_id, invocation_id)
            else:
                category = ("runner_request_conflict" if str(exc) == "runner_request_conflict"
                            else "runner_ack_identity_mismatch" if str(exc) ==
                            "runner_ack_identity_mismatch" else "runner_dispatch_error")
                self.store.record_runner_failure(run_id, invocation_id,
                                                 category=category)
            raise
        except Exception as exc:
            category = ("runner_binding_conflict" if isinstance(exc, LaunchError)
                        and str(exc) == "runner_binding_conflict" else
                        "runner_binding_write_error" if isinstance(exc, LaunchError)
                        else "runner_transport_error")
            try:
                self.store.record_runner_failure(run_id, invocation_id,
                                                 category=category)
            except Exception:
                pass  # Preserve the original binding or transport failure.
            raise
        if result.get("status") == "rejected" and not result.get("run_id"):
            self.store.record_runner_rejection(
                run_id, invocation_id,
                category=result.get("error_category") or "runner_rejected")
        if result.get("run_id"):
            self.store.record_runner_observation(
                run_id, invocation_id, provider="codex",
                runner_run_id=result["run_id"], kind="runner_status",
                payload={"status": result.get("status"),
                         "error_category": result.get("error_category")})
        return invocation_id, result

    def reconcile(self, run_id, invocation_id, execution_id):
        """Explicit read-only lookup; never repeats the native start request."""
        binding = self.store.trace_snapshot(run_id)["invocation"]
        if binding["invocation_id"] != invocation_id or not binding["runner_request_hash"]:
            raise LaunchError("runner_request_not_frozen")
        try:
            found = self.adapter.lookup_request("codex", binding["runner_request_id"])
        except Exception as exc:
            category = ("runner_lookup_conflict" if isinstance(exc, HandoffError)
                        and str(exc) == "runner_request_conflict" else
                        "runner_lookup_unknown")
            self.store.record_runner_failure(run_id, invocation_id,
                                             category=category)
            raise
        if found is None:
            self.store.record_runner_failure(run_id, invocation_id,
                                             category="runner_lookup_unknown")
            return None
        if (not isinstance(found, dict) or
                found.get("client_request_id") != binding["runner_request_id"] or
                found.get("request_hash") != binding["runner_request_hash"] or
                found.get("provider") != "codex"):
            self.store.record_runner_failure(run_id, invocation_id,
                                             category="runner_lookup_mismatch")
            raise LaunchError("runner_lookup_mismatch")
        try:
            self.store.bind_runner_ack(
                run_id, invocation_id, request_id=found["client_request_id"],
                provider="codex", runner_run_id=found.get("run_id"),
                raw_event_ref=found.get("raw_event_ref"))
        except LaunchError as exc:
            self.store.record_runner_failure(run_id, invocation_id,
                category=("runner_binding_conflict" if str(exc) ==
                          "runner_binding_conflict" else "runner_binding_write_error"))
            raise
        self.adapter.active[execution_id] = (self.adapter.endpoints["codex"],
                                             found["run_id"])
        self.store.record_runner_observation(
            run_id, invocation_id, provider="codex", runner_run_id=found["run_id"],
            kind="runner_status", payload={"status": found.get("status"),
                                            "reconciled": True})
        return found

    def cancel(self, run_id, invocation_id, execution_id):
        binding = self.store.trace_snapshot(run_id)["invocation"]
        if binding["invocation_id"] != invocation_id or not binding["runner_run_id"]:
            raise LaunchError("runner_observation_not_correlated")
        active = self.adapter.active.get(execution_id)
        if active is None or active[1] != binding["runner_run_id"]:
            raise LaunchError("runner_cancel_identity_mismatch")
        result = self.adapter.cancel(execution_id)
        self.store.record_runner_observation(
            run_id, invocation_id, provider=binding["runner_provider"],
            runner_run_id=binding["runner_run_id"], kind="runner_cancel",
            payload={"cancel_requested": result.get("cancel_requested"),
                     "cancel_confirmed": result.get("cancel_confirmed")})
        return result

    def observe_terminal(self, run_id, invocation_id):
        """Explicit authenticated status reconciliation; never starts a turn."""
        binding = self.store.trace_snapshot(run_id)["invocation"]
        if binding["invocation_id"] != invocation_id or not binding["runner_run_id"]:
            raise LaunchError("runner_observation_not_correlated")
        native = self.adapter.status(binding["runner_provider"], binding["runner_run_id"])
        if runner_attempt_terminal(native):
            self.store.record_runner_terminal(
                run_id, invocation_id, provider=binding["runner_provider"],
                runner_run_id=binding["runner_run_id"], status=native["status"],
                cancel_confirmed=native.get("cancel_confirmed") is True,
                attempt_finished=native.get("attempt_finished") is True)
        return native
