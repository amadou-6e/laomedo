"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

REFUSALS = {
    "runner_busy",
    "run_not_dispatchable",
    "resume_binding_mismatch",
    "post_run_snapshot_mismatch",
    "workspace_changed_since_snapshot",
    "protected_mount_changed",
    "activity_attempt_already_exists",
    "publication_handoff_resume_denied",
    "resume_after_runner_restart_forbidden",
    "resume_auth_identity_mismatch",
}
