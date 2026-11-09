"""Shared narrow issue identities and mutation payload validation."""

from laomedo.github.utils import labels_value
from laomedo.github.issues.models import GitHubIssue


def issue_value(raw, repository, number):
    """Validate a provider Issue and project its existing normalized payload.

    raw is the provider response; repository and number bind the expected target.
    Invalid identity, shape or field values raise the existing safe ValueError
    category. No network request, authorization or write occurs here.
    """
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
    """Admit the existing bounded close or field-update dictionary unchanged.

    Reject unsupported combinations or values with the resource-specific patch
    error. This validates content only and does not grant write authority.
    """
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
