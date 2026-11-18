"""Shared private-route request handling: admission, bounded JSON and safe failures.

Route modules for connections, private Skills and GitHub nodes import these
functions; none of them returns raw input, tokens or validation diagnostics.
"""

import json

from pydantic import ValidationError
from starlette.responses import JSONResponse

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
    GitHubConnectionInputError,
    GitHubOAuthError,
    GitHubReauthorizationRequired,
    GitHubRepositoryAccessError,
    GitHubTokenUnsupported,
)
from laomedo.github.connections.settings import CONNECTION_BODY_BYTES
from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
from laomedo.host.credentials.github.errors import GitHubVaultError
from laomedo.integrations.langflow.authentication.errors import (
    PrivateRequestRefused,
    PrivateSessionError,
    PrivateSessionRequired,
)
from laomedo.integrations.langflow.authentication.policy import PrivateGitHubAdmission


def refuse_duplicate_fields(pairs):
    """Refuse ambiguous repeated JSON fields before interpreting a control."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise GitHubConnectionInputError()
        result[key] = value
    return result


def private_failure_response(error):
    """Project only catalogued fixed codes, never token-bearing validation input."""
    if not isinstance(
        error,
        (
            GitHubConnectionError,
            GitHubOAuthError,
            GitHubVaultError,
            PrivateSessionError,
        ),
    ):
        error = GitHubConnectionError()
    status = 503
    if isinstance(error, (GitHubConnectionInputError, GitHubTokenUnsupported)):
        status = 400
    elif isinstance(
        error,
        (
            GitHubConnectionChanged,
            GitHubNodeAuthorizationError,
            GitHubReauthorizationRequired,
            GitHubRepositoryAccessError,
            PrivateSessionRequired,
            PrivateRequestRefused,
        ),
    ):
        status = 409
    return JSONResponse(
        {"code": error.code},
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def admit_private_request(request, user, *, mutating=False):
    """Derive owner/lease proof from upstream auth before reading a secret body."""
    policy = request.app.state.private_access_policy
    context = await policy.authorize(request, user)
    request.state.private_browser_context = context
    if mutating:
        policy.mutation(request, context)
    return PrivateGitHubAdmission(policy, context).scope()


async def read_private_json(request):
    """Read bounded JSON only; never echo raw payload or decode diagnostics."""
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise GitHubConnectionInputError()
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > CONNECTION_BODY_BYTES:
            raise GitHubConnectionInputError()
        data.extend(chunk)
    try:
        payload = json.loads(data, object_pairs_hook=refuse_duplicate_fields)
    except (ValueError, UnicodeError):
        raise GitHubConnectionInputError() from None
    if not isinstance(payload, dict):
        raise GitHubConnectionInputError()
    return payload


def parse_private_payload(model, payload):
    """Catch validation locally so FastAPI cannot serialize credential input."""
    try:
        return model.model_validate(payload)
    except ValidationError:
        raise GitHubConnectionInputError() from None
