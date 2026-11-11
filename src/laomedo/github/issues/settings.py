"""Fixed issues failure vocabulary; no settings instances."""

ERROR_CODES = frozenset(
    {
        "repository_url_invalid",
        "repository_connection_unavailable",
        "labels_invalid",
        "selected_label_unavailable",
        "issue_state_invalid",
        "selected_issue_invalid",
        "issue_operation_invalid",
        "issue_operation_conflict",
        "issue_grant_unavailable",
        "selected_issue_no_longer_matches",
        "github_discovery_incomplete",
        "issue_response_invalid",
        "issue_patch_invalid",
        "selected_issue_required",
        "issue_reference_mismatch",
        "issue_service_not_configured",
        "github_issue_unavailable",
        "issue_write_unknown",
        "invalid_request",
        "unauthorized",
        "github_http_401",
        "github_http_403",
        "github_http_404",
        "github_http_410",
    }
)


# These errors establish refusal before a mutation, not transport delivery failure.
PRE_DISPATCH_ERRORS = frozenset(
    {
        "repository_url_invalid",
        "repository_connection_unavailable",
        "labels_invalid",
        "selected_label_unavailable",
        "issue_state_invalid",
        "selected_issue_invalid",
        "issue_operation_invalid",
        "issue_operation_conflict",
        "issue_grant_unavailable",
        "selected_issue_no_longer_matches",
        "issue_patch_invalid",
        "selected_issue_required",
        "issue_reference_mismatch",
        "issue_service_not_configured",
        "invalid_request",
        "unauthorized",
    }
)
