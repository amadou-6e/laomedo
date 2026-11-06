"""Validate mediated requests against their authenticated host grant."""

from __future__ import annotations

from hashlib import sha256
import json
from laomedo.host.mediation.errors import MediationError
import re


def _request_hash(repository: str, operation: str, payload: dict) -> str:
    try:
        encoded = json.dumps(
            {"repository": repository, "operation": operation, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MediationError("request_not_serializable") from error
    if len(encoded) > 1024 * 1024:
        raise MediationError("request_too_large")
    return sha256(encoded).hexdigest()


def _target_key(repository: str, operation: str, payload: dict) -> str:
    if operation == "pr_create":
        target = ["pr", repository, payload["head"], payload["base"]]
    elif operation in {"pr_update", "pr_node_update"}:
        target = ["pr_update", repository, payload["number"]]
    elif operation == "issue_update":
        target = ["issue_update", repository, payload["number"]]
    elif operation == "issue_create":
        target = ["issue", repository, payload["reviewed_proposal_id"]]
    elif operation == "git_push":
        target = ["push", repository, payload["branch"]]
    else:
        target = [operation, repository]
    return json.dumps(target, separators=(",", ":"))


def _validate_effect(
    operation: str, payload: dict, grant, db, changes_workflow: bool | None
) -> None:
    """Enforce semantic approval before a generic API mutation is dispatched."""
    if operation == "git_push":
        if not all(
            isinstance(payload.get(key), str) and payload[key]
            for key in ("branch", "commit")
        ):
            raise MediationError("push_identity_required")
        if payload["branch"].startswith("refs/") or ".." in payload["branch"]:
            raise MediationError("push_branch_invalid")
        if payload["branch"] != grant["branch"]:
            raise MediationError("push_branch_denied")
        # The expensive trusted inspection was performed without a write
        # transaction. Revalidate the grant and branch inside this transaction.
        if changes_workflow is not False:
            raise MediationError(
                "workflow_approval_required"
                if changes_workflow is True
                else "push_diff_unverified"
            )
    if operation in {"pr_create", "pr_update"}:
        if not all(
            isinstance(payload.get(key), str) and payload[key]
            for key in ("head", "base", "marker")
        ):
            raise MediationError("pr_identity_required")
        if operation == "pr_update":
            if type(payload.get("number")) is not int or payload["number"] < 1:
                raise MediationError("target_pr_required")
            target = db.execute(
                "SELECT base FROM pr_targets WHERE grant_id=? AND number=?",
                (grant["grant_id"], payload["number"]),
            ).fetchone()
            if (
                target is None
                or payload["head"] != grant["branch"]
                or payload["base"] != target["base"]
            ):
                raise MediationError("target_pr_denied")
        if operation == "pr_create" and payload["head"] != grant["branch"]:
            raise MediationError("pr_head_denied")
        if operation == "pr_create" and payload["base"] != grant["base_branch"]:
            raise MediationError("pr_base_denied")
    if operation == "issue_create":
        if not all(
            isinstance(payload.get(key), str) and payload[key]
            for key in ("reviewed_proposal_id", "marker")
        ):
            raise MediationError("reviewed_issue_required")
        reviewed = json.loads(grant["reviewed_issue_hashes"])
        if reviewed.get(payload["reviewed_proposal_id"]) != _request_hash(
            grant["repository"], "issue_create", payload
        ):
            raise MediationError("issue_review_denied")
    if operation == "issue_update":
        from laomedo.github.issues.contract import (
            validate_patch as github_issues_contract_validate_patch,
        )

        try:
            if (
                set(payload) != {"number", "changes", "expected"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
                or not isinstance(payload["expected"], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", payload["expected"])
            ):
                raise ValueError()
            github_issues_contract_validate_patch(payload["changes"])
        except (ValueError, TypeError):
            raise MediationError("issue_patch_invalid") from None
        if (
            db.execute(
                "SELECT 1 FROM issue_targets WHERE grant_id=? AND number=?",
                (grant["grant_id"], payload["number"]),
            ).fetchone()
            is None
        ):
            raise MediationError("issue_target_denied")
    if operation == "pr_node_update":
        from laomedo.github.pull_requests.contract import (
            validate_patch as github_pull_requests_contract_validate_patch,
        )

        try:
            if (
                set(payload) != {"number", "changes", "expected", "head", "base"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
                or not isinstance(payload["expected"], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", payload["expected"])
            ):
                raise ValueError()
            github_pull_requests_contract_validate_patch(payload["changes"])
        except (ValueError, TypeError):
            raise MediationError("pr_patch_invalid") from None
        target = db.execute(
            "SELECT base FROM pr_targets WHERE grant_id=? AND number=?",
            (grant["grant_id"], payload["number"]),
        ).fetchone()
        if (
            target is None
            or payload["head"] != grant["branch"]
            or payload["base"] != target["base"]
        ):
            raise MediationError("target_pr_denied")
    if operation in {"api_rest_write", "api_graphql_mutation"}:
        # An agent-declared semantic_operation is not a security classifier.
        # The real endpoint/query parser must be reviewed before this lane opens.
        raise MediationError("api_write_unsupported")


def _validate_read(operation: str, payload: dict, repository: str, grant, db) -> None:
    if operation in {"label_list", "issue_query", "issue_read"}:
        from laomedo.github.issues.contract import labels_value

        try:
            if operation == "label_list" and payload != {}:
                raise ValueError()
            if operation == "issue_read" and (
                set(payload) != {"number"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
            ):
                raise ValueError()
            if operation == "issue_query":
                if set(payload) != {"labels", "state"} or payload["state"] not in {
                    "open",
                    "closed",
                    "all",
                }:
                    raise ValueError()
                labels_value(payload["labels"])
        except (ValueError, TypeError):
            raise MediationError("issue_read_request_invalid") from None
        return
    if operation == "git_fetch":
        if payload == {"action": "list"}:
            return
        if (
            set(payload) != {"action", "ref", "commit"}
            or payload.get("action") != "fetch"
            or payload.get("ref")
            not in {
                "refs/heads/" + grant["base_branch"],
                "refs/heads/" + grant["branch"],
            }
            or not isinstance(payload.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", payload["commit"])
        ):
            raise MediationError("fetch_target_denied")
        return
    if operation == "pr_read":
        if (
            set(payload) != {"number"}
            or type(payload["number"]) is not int
            or payload["number"] < 1
        ):
            raise MediationError("pr_read_target_invalid")
        target = db.execute(
            "SELECT base FROM pr_targets WHERE grant_id=? AND number=?",
            (grant["grant_id"], payload["number"]),
        ).fetchone()
        if target is None:
            raise MediationError("pr_read_target_denied")
        return
    if operation != "api_rest_read":
        return
    path = payload.get("path")
    prefix = f"/repos/{repository}/"
    if (
        payload.get("method", "GET") != "GET"
        or not isinstance(path, str)
        or not path.startswith(prefix)
        or any(part in path for part in ("..", "//", "\\", "%", "?", "#"))
    ):
        raise MediationError("api_read_denied")
