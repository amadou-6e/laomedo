"""Closed public failure vocabulary for the manual editing boundary."""

MANUAL_ERROR_CODES = frozenset(
    {
        "skill_manual_not_authorized",
        "skill_manual_stale",
        "skill_manual_invalid",
        "skill_manual_request_conflict",
        "skill_manual_policy_denied",
        "skill_manual_unavailable",
        "skill_manual_nothing_to_publish",
        "skill_manual_save_expired",
        "skill_manual_controls_unavailable",
        "skill_manual_comparison_unavailable",
    }
)
