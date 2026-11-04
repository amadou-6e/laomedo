"""Shared narrow issue identities and mutation payload validation."""

from laomedo.github.contract import labels_value
from laomedo.github.issues.models import GitHubIssue


def issue_value(raw, repository, number):
    if (
        not isinstance(raw, dict)
        or type(number) is not int
        or number < 1
        or raw.get("number") != number
        or "pull_request" in raw
        or raw.get("repository_url", "").lower()
        != "https://api.github.com/repos/" + repository.lower()
        or raw.get("html_url", "").lower()
        != f"https://github.com/{repository}/issues/{number}".lower()
        or not isinstance(raw.get("node_id"), str)
        or not raw["node_id"]
        or not isinstance(raw.get("updated_at"), str)
        or not raw["updated_at"]
        or not isinstance(raw.get("title"), str)
        or (raw.get("body") is not None and not isinstance(raw["body"], str))
        or raw.get("state") not in {"open", "closed"}
        or not isinstance(raw.get("labels"), list)
    ):
        raise ValueError("issue_response_invalid")
    names = []
    for label in raw["labels"]:
        if not isinstance(label, dict) or not isinstance(label.get("name"), str):
            raise ValueError("issue_response_invalid")
        names.append(label["name"])
    return GitHubIssue(
        repository=repository,
        number=number,
        url=raw["html_url"],
        node_id=raw["node_id"],
        title=raw["title"],
        body=raw.get("body") or "",
        labels=labels_value(names),
        state=raw["state"],
        updated_at=raw["updated_at"],
    ).to_payload()


def validate_patch(value):
    if (
        not isinstance(value, dict)
        or not value
        or not set(value) <= {"title", "body", "labels", "state"}
    ):
        raise ValueError("issue_patch_invalid")
    if "state" in value and value != {"state": "closed"}:
        raise ValueError("issue_patch_invalid")
    if "title" in value and (
        not isinstance(value["title"], str)
        or not value["title"].strip()
        or len(value["title"]) > 256
    ):
        raise ValueError("issue_patch_invalid")
    if "body" in value and (
        not isinstance(value["body"], str) or len(value["body"].encode()) > 256 * 1024
    ):
        raise ValueError("issue_patch_invalid")
    if "labels" in value:
        labels_value(value["labels"])
    return value


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
