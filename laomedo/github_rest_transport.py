"""Credential-owning, repository-bound REST transport for reviewed operations.

This is not a generic `gh api` tunnel or a `git push` implementation. The
token supplier belongs to the host service; an agent sees only a per-run
mediator capability. Unsupported operations fail explicitly.
"""

from __future__ import annotations

import json
import re
from urllib import error, parse, request

from .github_mediation import KnownRejected


_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
ISSUE_GRAPHQL_QUERY = 'query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issues(first:30,states:OPEN){nodes{number title body}}}}'


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class GitHubRestTransport:
    """Narrow first-slice adapter; never reads the ambient gh login."""

    def __init__(self, repository: str, token_supplier, *, opener=None):
        if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
            raise ValueError("repository_invalid")
        if token_supplier is None:
            raise ValueError("credential_supplier_required")
        self.repository = repository
        self.token_supplier = token_supplier
        self.opener = opener or request.build_opener(_NoRedirect)

    def __call__(self, repository: str, operation: str, payload: dict, *,
                 connection_id: str | None = None,
                 connection_generation: int | None = None) -> dict:
        if repository != self.repository:
            raise KnownRejected("repository_denied")
        prefix = f"/repos/{self.repository}"
        method, path, body = "GET", "", None
        if operation in {"pr_list", "issue_list"}:
            if operation == "issue_list" and payload == {"format": "fixed_graphql"}:
                owner, name = repository.split('/')
                response = self._call('POST', '/graphql', {
                    'query': ISSUE_GRAPHQL_QUERY, 'variables': {'owner': owner, 'name': name}},
                    connection_id, connection_generation)
                try:
                    nodes = response['data']['repository']['issues']['nodes']
                    if ('errors' in response or not isinstance(nodes, list) or len(nodes) > 30 or
                            any(not isinstance(item, dict) or type(item.get('number')) is not int or
                                item['number'] < 1 or not isinstance(item.get('title'), str) or
                                not isinstance(item.get('body'), str) for item in nodes)):
                        raise ValueError('graphql_response_invalid')
                except (KeyError, TypeError):
                    raise ValueError('graphql_response_invalid') from None
                return {'items': nodes}
            if payload != {}:
                raise KnownRejected("list_payload_invalid")
            path = prefix + ("/pulls" if operation == "pr_list" else "/issues")
            result = self._call("GET", path, None, connection_id,
                                connection_generation, allow_list=True)
            # GitHub's issues endpoint includes PRs; gh issue list does not.
            if operation == "issue_list":
                result["items"] = [item for item in result["items"]
                                   if "pull_request" not in item]
            return result
        if operation == "pr_create":
            if not all(isinstance(payload.get(k), str) and payload[k]
                       for k in ("title", "body", "head", "base", "marker")) or \
                    payload["marker"] not in payload["body"]:
                raise KnownRejected("pr_payload_invalid")
            method, path = "POST", prefix + "/pulls"
            body = {k: payload[k] for k in ("title", "body", "head", "base")}
            body["draft"] = payload.get("draft", False) is True
        elif operation == "pr_read":
            if set(payload) != {"number"} or type(payload["number"]) is not int or payload["number"] < 1:
                raise KnownRejected("pr_read_target_invalid")
            existing = self._call("GET", prefix + f"/pulls/{payload['number']}", None,
                                  connection_id, connection_generation)
            head = existing.get("head") or {}
            head_repo = head.get("repo") or {}
            base = existing.get("base") or {}
            if (existing.get("number") != payload["number"] or
                    head.get("repo") is None or head_repo.get("full_name") != repository or
                    not isinstance(head.get("ref"), str) or
                    not isinstance(head.get("sha"), str) or
                    not isinstance(base.get("ref"), str) or
                    not isinstance(existing.get("title"), str) or
                    not isinstance(existing.get("body"), str)):
                raise KnownRejected("pr_target_denied")
            return {"number": existing.get("number"), "title": existing.get("title"),
                    "body": existing.get("body"), "state": existing.get("state"),
                    "head": {"repository": repository, "branch": head["ref"],
                             "sha": head["sha"]}, "base": base["ref"]}
        elif operation == "pr_update":
            if type(payload.get("number")) is not int or payload["number"] < 1:
                raise KnownRejected("pr_payload_invalid")
            method, path = "PATCH", prefix + f"/pulls/{payload['number']}"
            body = {k: payload[k] for k in ("title", "body", "base")
                    if isinstance(payload.get(k), str)}
            if not body or ("body" in body and payload.get("marker") not in body["body"]):
                raise KnownRejected("pr_payload_invalid")
            expected = payload.get("expected")
            if (not isinstance(expected, dict) or
                    set(expected) != {"title", "body", "head_sha"} or
                    not all(isinstance(expected[k], str) for k in expected) or
                    not re.fullmatch(r"[0-9a-f]{40}", expected["head_sha"])):
                raise KnownRejected("pr_expected_snapshot_required")
            # The number alone is not authority: inspect the existing PR and
            # prove that its head is this run's approved branch in this repo.
            existing = self._call("GET", path, None, connection_id,
                                  connection_generation)
            head = existing.get("head") or {}
            head_repo = head.get("repo") or {}
            if (head.get("ref") != payload.get("head") or
                    head_repo.get("full_name") != repository or
                    (existing.get("base") or {}).get("ref") != payload.get("base")):
                raise KnownRejected("pr_target_denied")
            if (existing.get("title") != expected["title"] or
                    existing.get("body") != expected["body"] or
                    head.get("sha") != expected["head_sha"]):
                raise KnownRejected("pr_snapshot_changed")
            # GitHub offers no atomic compare-and-PATCH for this endpoint.
            # This catches preceding edits, not simultaneous ones. Verify by
            # a fresh read, never by trusting the PATCH response alone.
            self._call(method, path, body, connection_id, connection_generation)
            try:
                observed = self._call("GET", path, None, connection_id,
                                      connection_generation)
                observed_head = observed.get("head") or {}
                if (observed.get("number") != payload["number"] or
                        any(observed.get(k) != v for k, v in body.items()
                            if k != "base") or
                        (observed.get("base") or {}).get("ref") != payload["base"] or
                        observed_head.get("ref") != payload["head"] or
                        (observed_head.get("repo") or {}).get("full_name") != repository or
                        observed_head.get("sha") != expected["head_sha"]):
                    raise ValueError("pr_update_readback_mismatch")
                return observed
            except Exception:
                # Even a complete GET rejection cannot prove the earlier
                # PATCH had no effect. Preserve uncertainty in the journal.
                raise ValueError("pr_update_readback_unknown") from None
        elif operation == "issue_create":
            if not all(isinstance(payload.get(k), str) and payload[k]
                       for k in ("title", "body", "marker")) or \
                    payload["marker"] not in payload["body"]:
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
            if (not isinstance(suffix, str) or not suffix.startswith(prefix + "/") or
                    any(part in suffix for part in ("..", "//", "\\", "%", "?", "#"))):
                raise KnownRejected("api_path_denied")
            path = suffix
        else:
            raise KnownRejected("operation_not_implemented")

        return self._call(method, path, body, connection_id, connection_generation)

    def _call(self, method: str, path: str, body: dict | None,
              connection_id: str | None = None,
              connection_generation: int | None = None, *,
              allow_list: bool = False) -> dict:
        if (connection_id is None) != (connection_generation is None):
            raise KnownRejected("connection_binding_invalid")
        # Bound grants require a resolver accepting their exact identity and
        # generation. A legacy zero-argument supplier cannot serve them.
        try:
            token = (self.token_supplier() if connection_id is None else
                     self.token_supplier(connection_id, connection_generation))
        except (TypeError, KeyError, ValueError):
            raise KnownRejected("provider_credential_unavailable") from None
        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
            raise KnownRejected("provider_credential_unavailable")
        encoded = (json.dumps(body, separators=(",", ":")).encode("utf-8")
                   if body is not None else None)
        call = request.Request(
            "https://api.github.com" + path, data=encoded, method=method,
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": "Bearer " + token,
                     "X-GitHub-Api-Version": "2026-03-10",
                     "User-Agent": "laomedo-mediated-github/0.1"})
        if encoded is not None:
            call.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(call, timeout=15) as response:
                content = response.read(1024 * 1024 + 1)
                if len(content) > 1024 * 1024:
                    raise ValueError("response_too_large")
                value = json.loads(content)
                if allow_list:
                    if (not isinstance(value, list) or
                            any(not isinstance(item, dict) or
                                type(item.get("number")) is not int or
                                item["number"] < 1 for item in value)):
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
