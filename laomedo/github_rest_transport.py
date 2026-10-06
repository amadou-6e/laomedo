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

    def __call__(self, repository: str, operation: str, payload: dict) -> dict:
        if repository != self.repository:
            raise KnownRejected("repository_denied")
        prefix = f"/repos/{self.repository}"
        method, path, body = "GET", "", None
        if operation == "pr_create":
            if not all(isinstance(payload.get(k), str) and payload[k]
                       for k in ("title", "body", "head", "base", "marker")) or \
                    payload["marker"] not in payload["body"]:
                raise KnownRejected("pr_payload_invalid")
            method, path = "POST", prefix + "/pulls"
            body = {k: payload[k] for k in ("title", "body", "head", "base")}
            body["draft"] = payload.get("draft", False) is True
        elif operation == "pr_update":
            if type(payload.get("number")) is not int or payload["number"] < 1:
                raise KnownRejected("pr_payload_invalid")
            method, path = "PATCH", prefix + f"/pulls/{payload['number']}"
            body = {k: payload[k] for k in ("title", "body", "base")
                    if isinstance(payload.get(k), str)}
            if not body or ("body" in body and payload.get("marker") not in body["body"]):
                raise KnownRejected("pr_payload_invalid")
            # The number alone is not authority: inspect the existing PR and
            # prove that its head is this run's approved branch in this repo.
            existing = self._call("GET", path, None)
            head = existing.get("head") or {}
            head_repo = head.get("repo") or {}
            if (head.get("ref") != payload.get("head") or
                    head_repo.get("full_name") != repository):
                raise KnownRejected("pr_target_denied")
        elif operation == "issue_create":
            if not all(isinstance(payload.get(k), str) and payload[k]
                       for k in ("title", "body", "marker")) or \
                    payload["marker"] not in payload["body"]:
                raise KnownRejected("issue_payload_invalid")
            method, path = "POST", prefix + "/issues"
            body = {k: payload[k] for k in ("title", "body")}
        elif operation == "actions_read":
            job_id = payload.get("job_id")
            if type(job_id) is not int or job_id < 1:
                raise KnownRejected("actions_target_invalid")
            path = prefix + f"/actions/jobs/{job_id}"
        elif operation == "api_rest_read":
            suffix = payload.get("path")
            if (not isinstance(suffix, str) or not suffix.startswith(prefix + "/") or
                    any(part in suffix for part in ("..", "//", "\\", "%", "?", "#"))):
                raise KnownRejected("api_path_denied")
            path = suffix
        else:
            raise KnownRejected("operation_not_implemented")

        return self._call(method, path, body)

    def _call(self, method: str, path: str, body: dict | None) -> dict:
        token = self.token_supplier()
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
                if not isinstance(value, dict):
                    raise ValueError("response_invalid")
                return value
        except error.HTTPError as failure:
            # A complete, explicitly non-creating response is distinct from
            # a lost response or server error. Do not expose provider bodies.
            if failure.code in {400, 401, 403, 404, 410, 422}:
                raise KnownRejected(f"github_http_{failure.code}") from None
            raise
