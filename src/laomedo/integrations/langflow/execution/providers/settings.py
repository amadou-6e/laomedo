"""Fixed provider-worker protocol and data release fields; never graph configuration."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from laomedo.integrations.langflow.execution.worker.settings import GraphWorkerSettings


class ProviderAppSettings(BaseModel):
    """Explicit operator-installed UI/source and immutable isolated worker deployment."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    components: Path
    frontend: Path
    worker: GraphWorkerSettings


PROVIDER_WORKER_MODULE = "laomedo.integrations.langflow.execution.providers"
PROVIDER_EVENT_BYTES = 256 * 1024
PROVIDER_PROGRESS_QUEUE_SIZE = 64
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
