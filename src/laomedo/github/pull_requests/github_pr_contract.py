"""Typed PR-node records; public identities never authorize a write."""
import re
from laomedo.github.issues.github_issue_contract import repository_from_url, labels_value, issue_digest


pr_digest = issue_digest


def pr_value(raw, repository, number):
    if (not isinstance(raw, dict) or type(number) is not int or number < 1 or
            raw.get("number") != number or
            raw.get("html_url", "").lower() != f"https://github.com/{repository}/pull/{number}".lower() or
            not isinstance(raw.get("node_id"), str) or not raw["node_id"] or
            not isinstance(raw.get("updated_at"), str) or not raw["updated_at"] or
            not isinstance(raw.get("title"), str) or
            raw.get("body") is not None and not isinstance(raw["body"], str) or
            raw.get("state") not in {"open", "closed"} or type(raw.get("draft")) is not bool or
            not isinstance(raw.get("labels"), list)):
        raise ValueError("pr_response_invalid")
    head, base = raw.get("head") or {}, raw.get("base") or {}
    if (not isinstance(head.get("ref"), str) or not head["ref"] or
            not isinstance(head.get("sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", head["sha"]) or
            not isinstance(base.get("ref"), str) or not base["ref"] or
            (base.get("repo") or {}).get("full_name", "").lower() != repository.lower()):
        raise ValueError("pr_response_invalid")
    head_repository = (head.get("repo") or {}).get("full_name")
    if head_repository is not None and not isinstance(head_repository, str):
        raise ValueError("pr_response_invalid")
    try:
        labels = labels_value([label["name"] for label in raw["labels"]])
    except (KeyError, TypeError, ValueError):
        raise ValueError("pr_response_invalid") from None
    return {"repository": repository, "number": number, "url": raw["html_url"],
            "node_id": raw["node_id"], "title": raw["title"], "body": raw.get("body") or "",
            "labels": labels, "state": raw["state"], "draft": raw["draft"],
            "merged": bool(raw.get("merged_at")), "updated_at": raw["updated_at"],
            "head": {"repository": head_repository, "branch": head["ref"], "sha": head["sha"]},
            "base": base["ref"]}


def validate_patch(value):
    if not isinstance(value, dict) or not value or not set(value) <= {"title", "body", "labels", "state"}:
        raise ValueError("pr_patch_invalid")
    if "state" in value and value != {"state": "closed"}:
        raise ValueError("pr_patch_invalid")
    if "title" in value and (not isinstance(value["title"], str) or not value["title"].strip() or len(value["title"]) > 256):
        raise ValueError("pr_patch_invalid")
    if "body" in value and (not isinstance(value["body"], str) or len(value["body"].encode()) > 256 * 1024):
        raise ValueError("pr_patch_invalid")
    if "labels" in value:
        labels_value(value["labels"])
    return value


ERROR_CODES = frozenset({"repository_url_invalid", "repository_connection_unavailable", "labels_invalid",
    "selected_label_unavailable", "pr_state_invalid", "selected_pr_invalid", "pr_operation_invalid",
    "pr_operation_conflict", "pr_grant_unavailable", "selected_pr_no_longer_matches",
    "github_discovery_incomplete", "pr_response_invalid", "pr_patch_invalid", "selected_pr_required",
    "pr_reference_mismatch", "pr_service_not_configured", "github_pr_unavailable", "pr_write_unknown",
    "invalid_request", "unauthorized"})
PRE_DISPATCH_ERRORS = ERROR_CODES - {"github_pr_unavailable", "pr_write_unknown", "pr_response_invalid", "github_discovery_incomplete"}
ERROR_CODES = ERROR_CODES | {'pr_agent_loop_invalid','pr_agent_failed','pr_agent_cancelled','pr_changed_since_agent_read'}
PRE_DISPATCH_ERRORS = PRE_DISPATCH_ERRORS | {'pr_agent_loop_invalid','pr_agent_failed','pr_agent_cancelled','pr_changed_since_agent_read'}
ERROR_CODES = ERROR_CODES | {'pr_feedback_not_configured','pr_feedback_ticket_invalid'}
PRE_DISPATCH_ERRORS = PRE_DISPATCH_ERRORS | {'pr_feedback_not_configured','pr_feedback_ticket_invalid'}
