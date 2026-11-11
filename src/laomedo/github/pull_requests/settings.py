"""Fixed pull requests failure vocabulary; no settings instances."""

ERROR_CODES = frozenset(
    {
        "repository_url_invalid",
        "repository_connection_unavailable",
        "labels_invalid",
        "selected_label_unavailable",
        "pr_state_invalid",
        "selected_pr_invalid",
        "pr_operation_invalid",
        "pr_operation_conflict",
        "pr_grant_unavailable",
        "selected_pr_no_longer_matches",
        "github_discovery_incomplete",
        "pr_response_invalid",
        "pr_patch_invalid",
        "selected_pr_required",
        "pr_reference_mismatch",
        "pr_service_not_configured",
        "github_pr_unavailable",
        "pr_write_unknown",
        "invalid_request",
        "unauthorized",
    }
)
PRE_DISPATCH_ERRORS = ERROR_CODES - {
    "github_pr_unavailable",
    "pr_write_unknown",
    "pr_response_invalid",
    "github_discovery_incomplete",
}
ERROR_CODES = ERROR_CODES | {
    "pr_agent_loop_invalid",
    "pr_agent_failed",
    "pr_agent_cancelled",
    "pr_changed_since_agent_read",
}
PRE_DISPATCH_ERRORS = PRE_DISPATCH_ERRORS | {
    "pr_agent_loop_invalid",
    "pr_agent_failed",
    "pr_agent_cancelled",
    "pr_changed_since_agent_read",
}
ERROR_CODES = ERROR_CODES | {"pr_feedback_not_configured", "pr_feedback_ticket_invalid"}
PRE_DISPATCH_ERRORS = PRE_DISPATCH_ERRORS | {
    "pr_feedback_not_configured",
    "pr_feedback_ticket_invalid",
}
