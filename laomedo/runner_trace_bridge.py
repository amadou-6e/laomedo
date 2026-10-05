"""First-slice, single-invocation bridge from native runner to durable trace.

Langflow remains responsible for workflow scheduling. This bridge only reserves
and correlates one fresh native invocation; it never retries an uncertain POST.
"""

from .handoffs import HandoffError
from .workflow_run_store import LaunchError


class RunnerTraceBridge:
    def __init__(self, store, adapter):
        self.store = store
        self.adapter = adapter

    def dispatch(self, run_id, stage_id, handoff, *, deadline, cancelled):
        if (handoff.get("operation") != "fresh" or
                handoff.get("target", {}).get("provider") != "codex"):
            raise LaunchError("first_slice_requires_fresh_codex")
        invocation_id = self.store.reserve_invocation(run_id, stage_id)
        self.store.begin_invocation(run_id, invocation_id)
        def on_ack(ack):
            self.store.bind_runner_ack(
                run_id, invocation_id, request_id=ack["client_request_id"],
                provider="codex", runner_run_id=ack["run_id"],
                raw_event_ref=ack["raw_event_ref"])
        try:
            result = self.adapter.dispatch(
                handoff, deadline=deadline, cancelled=cancelled, early_start=True,
                runner_request_id=invocation_id, on_ack=on_ack)
        except HandoffError as exc:
            if str(exc) == "runner_result_pending":
                self.store.record_runner_wait_uncertain(run_id, invocation_id)
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
