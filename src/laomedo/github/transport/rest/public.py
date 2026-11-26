"""Anonymous delivery of public issue reads for one host-configured repository."""

import json
from urllib import error, request

from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.mediation.errors import KnownRejected


class PublicGitHubIssueTransport(GitHubRestTransport):
    """Permit only bounded, credential-free GitHub issue and label reads."""

    def __init__(self, repository, *, opener=None):
        if not isinstance(repository, str) or any(
            part in {".", ".."} for part in repository.split("/")
        ):
            raise ValueError("repository_invalid")
        super().__init__(repository, self._no_credential, opener=opener)

    def __call__(self, repository, operation, payload, **kwargs):
        if operation not in {"issue_read", "issue_query", "label_list"}:
            raise KnownRejected("operation_not_implemented")
        return super().__call__(repository, operation, payload, **kwargs)

    @staticmethod
    def _no_credential():
        return None

    def _call(
        self,
        method,
        path,
        body,
        connection_id=None,
        connection_generation=None,
        *,
        allow_list=False,
        label_list=False,
        timeout=15,
    ):
        if (
            method != "GET"
            or body is not None
            or connection_id is not None
            or connection_generation is not None
        ):
            raise KnownRejected("operation_not_implemented")
        call = request.Request(
            "https://api.github.com" + path,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "laomedo-public-issue/0.1",
            },
        )
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
            if failure.code in {400, 401, 403, 404, 410, 422}:
                raise KnownRejected(f"github_http_{failure.code}") from None
            raise
