"""Fixed provider-worker protocol and data release fields; never graph configuration."""

PROVIDER_WORKER_MODULE = "laomedo.integrations.langflow.execution.providers"
PROVIDER_STATUS_FIELDS = frozenset(
    {
        "run_id",
        "status",
        "answer",
        "client_request_id",
        "request_hash",
        "provider",
        "requested_model",
        "requested_effort",
        "thread_id",
        "post_run_hash",
        "raw_event_ref",
        "output_ref",
        "snapshot_ready",
        "attempt_finished",
        "cancel_requested",
        "cancel_confirmed",
        "error_category",
        "precheck",
        "evidence_complete",
        "completion_basis",
        "requirements_revision",
        "usage",
        "skills",
        "skill",
        "activity_initial_attempt_id",
    }
)
