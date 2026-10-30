"""Shared HTTP limits, snapshot bounds and runner startup configuration."""

MAX_BODY = 64 * 1024


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read at point of use; no cached environment, dotenv or credential contents.

    Strings preserve missing/empty values and exact ``== "1"`` flag behavior.
    Existing consumers own URL/path validation and stable public errors.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        secrets_dir=None,
        env_nested_delimiter=None,
        enable_decoding=False,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Only explicit arguments and the process environment supply settings."""
        return init_settings, env_settings

    startup_gate: str | None = Field(
        default=None, validation_alias="LAOMEDO_STARTUP_GATE", repr=False, exclude=True
    )


# Fixed redaction policy from pinned SDK literals; never user configuration.
SDK_FAILURE_CODES = {
    "CleanupUnconfirmedError": "docker_cleanup_unconfirmed",
    "ConnectionConfigurationError": "docker_connection_configuration_invalid",
    "CreationRejectedError": "docker_creation_rejected",
    "CreationUnconfirmedError": "docker_creation_unconfirmed",
    "DeadlineError": "docker_deadline_exceeded",
    "DockerOperationError": "docker_operation_failed",
    "ImageResolutionError": "docker_image_resolution_failed",
    "JobCancelledError": "docker_job_cancelled",
    "OutputLimitError": "docker_output_limit_exceeded",
    "OwnershipConflictError": "docker_resource_ownership_conflict",
    "PendingReceiptError": "docker_receipt_pending",
    "ReceiptInUseError": "docker_receipt_in_use",
}

SDK_FAILURE_OPERATIONS = frozenset(
    (
        "acquire container receipt",
        "cancel container job",
        "cancel container job before dispatch",
        "clear unstarted container receipt",
        "close session on its creator thread",
        "confirm container exit after output EOF",
        "confirm container exit status",
        "confirm container removal",
        "confirm container running state",
        "confirm loopback published port",
        "confirm newly created container exists",
        "confirm owned container cleanup",
        "create container",
        "evaluate container stop condition",
        "inspect container",
        "lock private container receipt",
        "match container reservation",
        "mix container frame and line readers",
        "monitor session on its creator thread",
        "open interactive session",
        "open private container receipt",
        "preserve pending container receipt",
        "read private container receipt",
        "reconcile container creation",
        "reconcile unobserved container creation",
        "record observed container identity",
        "record original container endpoint",
        "release private container receipt",
        "remove container",
        "resolve container image",
        "run one-shot container",
        "start container",
        "start container stop monitor",
        "start missing container",
        "validate container receipt",
        "verify attached stdin closure",
        "verify container bind mounts",
        "verify container host aliases",
        "verify container init and CPU quota",
        "verify container ownership",
        "verify container process configuration",
        "verify container sandbox configuration",
        "verify container sandbox permissions",
        "verify container stdin and terminal",
        "verify explicit container environment",
        "verify explicit container mounts",
        "verify local bind mount source exists",
        "verify loopback port bindings",
        "verify original container endpoint",
        "verify unstarted container receipt",
        "wait for container exit",
        "wait for missing container",
        "write private container receipt",
    )
)

RUNNER_FAILURE_CODES = frozenset(
    (
        "activity_attempt_already_exists",
        "app_owned_auth_requires_split_executor",
        "auth_revoked_during_turn",
        "auth_store_overlaps_runner_state",
        "cancelled_before_turn",
        "cancelled_by_user",
        "completed_without_agent_message",
        "conflicting_split_auth_sources",
        "container_termination_unverified",
        "docker_control_failed",
        "docker_image_digest_changed",
        "executor_not_ready",
        "executor_termination_unverified",
        "git_image_missing_git",
        "git_workspace_split_unsupported",
        "initialize_rejected",
        "invalid_activity_attempt_id",
        "invalid_local_image_id",
        "invalid_request",
        "invalid_task",
        "invalid_worker_command",
        "lease_service_lost",
        "lease_service_required",
        "lease_service_unavailable",
        "lease_service_unverified",
        "mediated_capability_unavailable",
        "mediated_command_scope_missing",
        "mediated_grant_unavailable",
        "model_list_invalid_cursor",
        "model_list_invalid_entry",
        "model_list_page_limit",
        "model_list_rejected",
        "opencode_cancelled_before_dispatch",
        "opencode_command_service_closed",
        "opencode_console_provider_routing_not_allowed",
        "opencode_container_cleanup_unverified",
        "opencode_container_configuration_invalid",
        "opencode_controller_image_unavailable",
        "opencode_controller_startup_failed",
        "opencode_image_pin_mismatch",
        "opencode_isolated_transport_required",
        "opencode_model_discovery_in_progress",
        "opencode_model_not_connected",
        "opencode_organization_context_invalid",
        "opencode_output_requirements_not_supported",
        "opencode_outstanding_tool",
        "opencode_private_auth_required",
        "opencode_provider_model_required",
        "opencode_response_not_terminal",
        "opencode_runtime_pin_mismatch",
        "opencode_transport_cleanup_failed",
        "opencode_workspace_command_failed",
        "outstanding_command_completion_unknown",
        "permission_config_changed",
        "permission_preflight_failed",
        "pinned_skill_record_invalid",
        "pinned_skill_workspace_changed",
        "post_run_snapshot_mismatch",
        "protected_mount_changed",
        "publication_handoff_resume_denied",
        "resume_after_runner_restart_forbidden",
        "resume_auth_identity_mismatch",
        "resume_binding_mismatch",
        "resume_provider_binding_mismatch",
        "run_not_active_in_this_process",
        "run_not_dispatchable",
        "runner_busy",
        "runner_docker_check_unconfirmed",
        "runner_transport_failed",
        "split_executor_lease_unavailable",
        "split_executor_requires_native_transport",
        "split_provider_requires_split_executor",
        "thread_identity_mismatch",
        "unknown_worker_tool",
        "unsupported_codex_cli_version",
        "unsupported_model_effort",
        "unsupported_opencode_effort",
        "unsupported_opencode_skill_name",
        "workspace_changed_since_snapshot",
        "workspace_copy_mismatch",
    )
)
