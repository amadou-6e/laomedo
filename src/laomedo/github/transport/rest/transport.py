"""Credential-owning, repository-bound REST transport for reviewed operations.

This is not a generic `gh api` tunnel or a `git push` implementation. The
token supplier belongs to the host service; an agent sees only a per-run
mediator capability. Unsupported operations fail explicitly.
"""

from __future__ import annotations

from laomedo.http.redirect import NoRedirect
from laomedo.github.contract import issue_digest
from laomedo.github.issues.contract import issue_value
from laomedo.github.contract import labels_value
from laomedo.github.issues.contract import validate_patch
from laomedo.github.contract import issue_digest as pr_digest
from laomedo.github.pull_requests.contract import pr_value
from laomedo.github.pull_requests.contract import validate_patch as pr_validate_patch
from laomedo.host.mediation.errors import KnownRejected

from urllib import error
from urllib import parse
from urllib import request
import json
import re
import time

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
ISSUE_GRAPHQL_QUERY = "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issues(first:30,states:OPEN){nodes{number title body}}}}"


class GitHubRestTransport:
    """Narrow first-slice adapter; never reads the ambient gh login."""

    def __init__(self, repository: str, token_supplier, *, opener=None):
        if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
            raise ValueError("repository_invalid")
        if token_supplier is None:
            raise ValueError("credential_supplier_required")
        self.repository = repository
        self.token_supplier = token_supplier
        self.opener = opener or request.build_opener(NoRedirect)

    def __call__(
        self,
        repository: str,
        operation: str,
        payload: dict,
        *,
        connection_id: str | None = None,
        connection_generation: int | None = None,
        before_write=None,
    ) -> dict:
        if repository != self.repository:
            raise KnownRejected("repository_denied")
        prefix = f"/repos/{self.repository}"
        method, path, body = "GET", "", None
        if operation == "pr_node_query":
            if set(payload) != {"labels", "state"} or payload["state"] not in {
                "open",
                "closed",
                "all",
            }:
                raise KnownRejected("prs_request_invalid")
            selected = set(labels_value(payload["labels"]))
            raw = self._pages(
                prefix + "/pulls",
                connection_id,
                connection_generation,
                query={"state": payload["state"]},
            )
            prs = [pr_value(item, repository, item["number"]) for item in raw]
            return {"items": [item for item in prs if selected <= set(item["labels"])]}
        if operation == "pr_node_read":
            if (
                set(payload) != {"number"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
            ):
                raise KnownRejected("pr_read_target_invalid")
            return pr_value(
                self._call(
                    "GET",
                    prefix + f"/pulls/{payload['number']}",
                    None,
                    connection_id,
                    connection_generation,
                ),
                repository,
                payload["number"],
            )
        if operation == "pr_node_update":
            try:
                if set(payload) != {"number", "changes", "expected", "head", "base"}:
                    raise ValueError()
                changes = pr_validate_patch(payload["changes"])
            except (ValueError, TypeError):
                raise KnownRejected("pr_patch_invalid") from None
            current = self(
                repository,
                "pr_node_read",
                {"number": payload["number"]},
                connection_id=connection_id,
                connection_generation=connection_generation,
            )
            if (
                current["head"]["repository"] != repository
                or current["head"]["branch"] != payload["head"]
                or current["base"] != payload["base"]
                or current["merged"]
            ):
                raise KnownRejected("pr_target_denied")
            if pr_digest(current) != payload["expected"]:
                raise KnownRejected("pr_changed_since_read")
            if before_write is None:
                raise KnownRejected("pr_write_guard_required")
            if "labels" in changes:
                available = {
                    x["name"]
                    for x in self._pages(
                        prefix + "/labels",
                        connection_id,
                        connection_generation,
                        label_list=True,
                    )
                }
                if not set(changes["labels"]) <= available:
                    raise KnownRejected("pr_labels_unknown")
            metadata = {key: value for key, value in changes.items() if key != "labels"}
            wrote = False
            try:
                acknowledged = current
                if metadata:
                    before_write()
                    acknowledged = pr_value(
                        self._call(
                            "PATCH",
                            prefix + f"/pulls/{payload['number']}",
                            metadata,
                            connection_id,
                            connection_generation,
                        ),
                        repository,
                        payload["number"],
                    )
                    wrote = True
                if "labels" in changes:
                    # Labels use GitHub's issue-label endpoint, after proving the target is a PR.
                    observed = self(
                        repository,
                        "pr_node_read",
                        {"number": payload["number"]},
                        connection_id=connection_id,
                        connection_generation=connection_generation,
                    )
                    if pr_digest(observed) != pr_digest(acknowledged):
                        raise ValueError("pr_update_readback_unknown")
                    before_write()
                    self._call(
                        "PUT",
                        prefix + f"/issues/{payload['number']}/labels",
                        {"labels": changes["labels"]},
                        connection_id,
                        connection_generation,
                        allow_list=True,
                        label_list=True,
                    )
                    wrote = True
                confirmed = self(
                    repository,
                    "pr_node_read",
                    {"number": payload["number"]},
                    connection_id=connection_id,
                    connection_generation=connection_generation,
                )
                if (
                    confirmed["node_id"] != current["node_id"]
                    or confirmed["head"] != current["head"]
                    or confirmed["base"] != current["base"]
                    or any(
                        confirmed[key] != (sorted(value) if key == "labels" else value)
                        for key, value in changes.items()
                    )
                ):
                    raise ValueError("pr_update_readback_unknown")
                return confirmed
            except KnownRejected:
                if wrote:
                    raise ValueError("pr_partial_update_unknown") from None
                raise
        if operation == "label_list":
            if payload != {}:
                raise KnownRejected("labels_request_invalid")
            return {
                "items": self._pages(
                    prefix + "/labels",
                    connection_id,
                    connection_generation,
                    label_list=True,
                )
            }
        if operation == "issue_query":
            if set(payload) != {"labels", "state"} or payload["state"] not in {
                "open",
                "closed",
                "all",
            }:
                raise KnownRejected("issues_request_invalid")
            selected = set(labels_value(payload["labels"]))
            raw = self._pages(
                prefix + "/issues",
                connection_id,
                connection_generation,
                query={"state": payload["state"]},
            )
            issues = [
                issue_value(item, repository, item["number"])
                for item in raw
                if "pull_request" not in item
            ]
            return {
                "items": [item for item in issues if selected <= set(item["labels"])]
            }
        if operation == "issue_read":
            if (
                set(payload) != {"number"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
            ):
                raise KnownRejected("issue_read_target_invalid")
            raw = self._call(
                "GET",
                prefix + f"/issues/{payload['number']}",
                None,
                connection_id,
                connection_generation,
            )
            return issue_value(raw, repository, payload["number"])
        if operation == "issue_update":
            if (
                set(payload) != {"number", "changes", "expected"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
            ):
                raise KnownRejected("issue_patch_invalid")
            try:
                changes = validate_patch(payload["changes"])
            except ValueError:
                raise KnownRejected("issue_patch_invalid") from None
            current = self(
                repository,
                "issue_read",
                {"number": payload["number"]},
                connection_id=connection_id,
                connection_generation=connection_generation,
            )
            if issue_digest(current) != payload["expected"]:
                raise KnownRejected("issue_changed_since_read")
            if "labels" in changes:
                available = {
                    x["name"]
                    for x in self._pages(
                        prefix + "/labels",
                        connection_id,
                        connection_generation,
                        label_list=True,
                    )
                }
                if not set(changes["labels"]) <= available:
                    raise KnownRejected("issue_labels_unknown")
            path = prefix + f"/issues/{payload['number']}"
            if before_write is None:
                raise KnownRejected("issue_write_guard_required")
            before_write()
            acknowledged = issue_value(
                self._call(
                    "PATCH", path, changes, connection_id, connection_generation
                ),
                repository,
                payload["number"],
            )
            try:
                confirmed = self(
                    repository,
                    "issue_read",
                    {"number": payload["number"]},
                    connection_id=connection_id,
                    connection_generation=connection_generation,
                )
            except Exception:
                # The PATCH was acknowledged; a rejected/lost readback is still uncertain.
                raise ValueError("issue_update_readback_unknown") from None
            if (
                acknowledged["node_id"] != current["node_id"]
                or confirmed["node_id"] != current["node_id"]
            ):
                raise ValueError("issue_update_readback_unknown")
            for key, value in changes.items():
                expected = sorted(value) if key == "labels" else value
                if acknowledged[key] != expected or confirmed[key] != expected:
                    raise ValueError("issue_update_readback_unknown")
            return confirmed
        if operation in {"pr_list", "issue_list"}:
            if operation == "issue_list" and payload == {"format": "fixed_graphql"}:
                owner, name = repository.split("/")
                response = self._call(
                    "POST",
                    "/graphql",
                    {
                        "query": ISSUE_GRAPHQL_QUERY,
                        "variables": {"owner": owner, "name": name},
                    },
                    connection_id,
                    connection_generation,
                )
                try:
                    nodes = response["data"]["repository"]["issues"]["nodes"]
                    if (
                        "errors" in response
                        or not isinstance(nodes, list)
                        or len(nodes) > 30
                        or any(
                            not isinstance(item, dict)
                            or type(item.get("number")) is not int
                            or item["number"] < 1
                            or not isinstance(item.get("title"), str)
                            or not isinstance(item.get("body"), str)
                            for item in nodes
                        )
                    ):
                        raise ValueError("graphql_response_invalid")
                except (KeyError, TypeError):
                    raise ValueError("graphql_response_invalid") from None
                return {"items": nodes}
            if payload != {}:
                raise KnownRejected("list_payload_invalid")
            path = prefix + ("/pulls" if operation == "pr_list" else "/issues")
            result = self._call(
                "GET", path, None, connection_id, connection_generation, allow_list=True
            )
            # GitHub's issues endpoint includes PRs; gh issue list does not.
            if operation == "issue_list":
                result["items"] = [
                    item for item in result["items"] if "pull_request" not in item
                ]
            return result
        if operation == "pr_create":
            if (
                not all(
                    isinstance(payload.get(k), str) and payload[k]
                    for k in ("title", "body", "head", "base", "marker")
                )
                or payload["marker"] not in payload["body"]
            ):
                raise KnownRejected("pr_payload_invalid")
            method, path = "POST", prefix + "/pulls"
            body = {k: payload[k] for k in ("title", "body", "head", "base")}
            body["draft"] = payload.get("draft", False) is True
        elif operation == "pr_read":
            if (
                set(payload) != {"number"}
                or type(payload["number"]) is not int
                or payload["number"] < 1
            ):
                raise KnownRejected("pr_read_target_invalid")
            existing = self._call(
                "GET",
                prefix + f"/pulls/{payload['number']}",
                None,
                connection_id,
                connection_generation,
            )
            head = existing.get("head") or {}
            head_repo = head.get("repo") or {}
            base = existing.get("base") or {}
            if (
                existing.get("number") != payload["number"]
                or head.get("repo") is None
                or head_repo.get("full_name") != repository
                or not isinstance(head.get("ref"), str)
                or not isinstance(head.get("sha"), str)
                or not isinstance(base.get("ref"), str)
                or not isinstance(existing.get("title"), str)
                or not isinstance(existing.get("body"), str)
            ):
                raise KnownRejected("pr_target_denied")
            return {
                "number": existing.get("number"),
                "title": existing.get("title"),
                "body": existing.get("body"),
                "state": existing.get("state"),
                "head": {
                    "repository": repository,
                    "branch": head["ref"],
                    "sha": head["sha"],
                },
                "base": base["ref"],
            }
        elif operation == "pr_update":
            if type(payload.get("number")) is not int or payload["number"] < 1:
                raise KnownRejected("pr_payload_invalid")
            method, path = "PATCH", prefix + f"/pulls/{payload['number']}"
            body = {
                k: payload[k]
                for k in ("title", "body", "base")
                if isinstance(payload.get(k), str)
            }
            if not body or (
                "body" in body and payload.get("marker") not in body["body"]
            ):
                raise KnownRejected("pr_payload_invalid")
            expected = payload.get("expected")
            if (
                not isinstance(expected, dict)
                or set(expected) != {"title", "body", "head_sha"}
                or not all(isinstance(expected[k], str) for k in expected)
                or not re.fullmatch(r"[0-9a-f]{40}", expected["head_sha"])
            ):
                raise KnownRejected("pr_expected_snapshot_required")
            # The number alone is not authority: inspect the existing PR and
            # prove that its head is this run's approved branch in this repo.
            existing = self._call(
                "GET", path, None, connection_id, connection_generation
            )
            head = existing.get("head") or {}
            head_repo = head.get("repo") or {}
            if (
                head.get("ref") != payload.get("head")
                or head_repo.get("full_name") != repository
                or (existing.get("base") or {}).get("ref") != payload.get("base")
            ):
                raise KnownRejected("pr_target_denied")
            if (
                existing.get("title") != expected["title"]
                or existing.get("body") != expected["body"]
                or head.get("sha") != expected["head_sha"]
            ):
                raise KnownRejected("pr_snapshot_changed")
            # GitHub offers no atomic compare-and-PATCH for this endpoint.
            # This catches preceding edits, not simultaneous ones. Verify by
            # a fresh read, never by trusting the PATCH response alone.
            self._call(method, path, body, connection_id, connection_generation)
            try:
                observed = self._call(
                    "GET", path, None, connection_id, connection_generation
                )
                observed_head = observed.get("head") or {}
                if (
                    observed.get("number") != payload["number"]
                    or any(observed.get(k) != v for k, v in body.items() if k != "base")
                    or (observed.get("base") or {}).get("ref") != payload["base"]
                    or observed_head.get("ref") != payload["head"]
                    or (observed_head.get("repo") or {}).get("full_name") != repository
                    or observed_head.get("sha") != expected["head_sha"]
                ):
                    raise ValueError("pr_update_readback_mismatch")
                return observed
            except Exception:
                # Even a complete GET rejection cannot prove the earlier
                # PATCH had no effect. Preserve uncertainty in the journal.
                raise ValueError("pr_update_readback_unknown") from None
        elif operation == "issue_create":
            if (
                not all(
                    isinstance(payload.get(k), str) and payload[k]
                    for k in ("title", "body", "marker")
                )
                or payload["marker"] not in payload["body"]
            ):
                raise KnownRejected("issue_payload_invalid")
            method, path = "POST", prefix + "/issues"
            body = {k: payload[k] for k in ("title", "body")}
        elif operation == "actions_read":
            job_id = payload.get("job_id")
            if payload == {"resource": "runs"}:
                path = prefix + "/actions/runs"
            elif type(job_id) is int and job_id > 0 and len(payload) == 1:
                path = prefix + f"/actions/jobs/{job_id}"
            else:
                raise KnownRejected("actions_target_invalid")
        elif operation == "api_rest_read":
            suffix = payload.get("path")
            if (
                not isinstance(suffix, str)
                or not suffix.startswith(prefix + "/")
                or any(part in suffix for part in ("..", "//", "\\", "%", "?", "#"))
            ):
                raise KnownRejected("api_path_denied")
            path = suffix
        else:
            raise KnownRejected("operation_not_implemented")

        return self._call(method, path, body, connection_id, connection_generation)

    def _pages(self, path, connection_id, generation, *, query=None, label_list=False):
        items = []
        deadline = time.monotonic() + 60
        for page in range(1, 11):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("github_discovery_incomplete")
            suffix = parse.urlencode({**(query or {}), "per_page": 100, "page": page})
            result = self._call(
                "GET",
                path + "?" + suffix,
                None,
                connection_id,
                generation,
                allow_list=True,
                label_list=label_list,
                timeout=min(15, remaining),
            )
            batch = result["items"]
            if len(batch) > 100:
                raise ValueError("github_discovery_incomplete")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise ValueError("github_discovery_incomplete")

    def _call(
        self,
        method: str,
        path: str,
        body: dict | None,
        connection_id: str | None = None,
        connection_generation: int | None = None,
        *,
        allow_list: bool = False,
        label_list: bool = False,
        timeout: float = 15,
    ) -> dict:
        if (connection_id is None) != (connection_generation is None):
            raise KnownRejected("connection_binding_invalid")
        # Bound grants require a resolver accepting their exact identity and
        # generation. A legacy zero-argument supplier cannot serve them.
        try:
            token = (
                self.token_supplier()
                if connection_id is None
                else self.token_supplier(connection_id, connection_generation)
            )
        except (TypeError, KeyError, ValueError):
            raise KnownRejected("provider_credential_unavailable") from None
        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
            raise KnownRejected("provider_credential_unavailable")
        encoded = (
            json.dumps(body, separators=(",", ":")).encode("utf-8")
            if body is not None
            else None
        )
        call = request.Request(
            "https://api.github.com" + path,
            data=encoded,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + token,
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "laomedo-mediated-github/0.1",
            },
        )
        if encoded is not None:
            call.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(call, timeout=timeout) as response:
                content = response.read(1024 * 1024 + 1)
                if len(content) > 1024 * 1024:
                    raise ValueError("response_too_large")
                value = json.loads(content)
                if allow_list:
                    if not isinstance(value, list) or any(
                        not isinstance(item, dict)
                        or (
                            (not isinstance(item.get("name"), str) or not item["name"])
                            if label_list
                            else (
                                type(item.get("number")) is not int
                                or item["number"] < 1
                            )
                        )
                        for item in value
                    ):
                        raise ValueError("list_response_invalid")
                    return {"items": value}
                if not isinstance(value, dict):
                    raise ValueError("response_invalid")
                return value
        except error.HTTPError as failure:
            # A complete, explicitly non-creating response is distinct from
            # a lost response or server error. Do not expose provider bodies.
            if failure.code in {400, 401, 403, 404, 410, 422}:
                raise KnownRejected(f"github_http_{failure.code}") from None
            raise
