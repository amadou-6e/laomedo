"""Private browser connection routes; credentials never pass public service adapters."""

import json
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from langflow.api.utils import CurrentActiveUser
from pydantic import SecretStr, ValidationError
from starlette.responses import JSONResponse, RedirectResponse

from laomedo.github.connections.errors import (
    GitHubConnectionChanged,
    GitHubConnectionError,
    GitHubConnectionInputError,
    GitHubOAuthError,
    GitHubReauthorizationRequired,
    GitHubRepositoryAccessError,
    GitHubTokenUnsupported,
)
from laomedo.github.connections.models import (
    GitHubAppSetupRequest,
    GitHubBrowserConnectRequest,
    GitHubConnectionRequest,
    GitHubConsentRequest,
    GitHubDisconnectRequest,
    GitHubPendingRequest,
    GitHubResponseBinding,
    GitHubTokenConnectRequest,
)
from laomedo.github.connections.settings import CONNECTION_BODY_BYTES
from laomedo.host.credentials.github.errors import GitHubVaultError
from laomedo.integrations.langflow.authentication.errors import (
    PrivateRequestRefused,
    PrivateSessionError,
    PrivateSessionRequired,
)
from laomedo.integrations.langflow.authentication.policy import PrivateGitHubAdmission

connection_router = APIRouter(
    prefix="/api/v1/laomedo", tags=["Private GitHub connections"]
)


def _unique_fields(pairs):
    """Refuse ambiguous repeated JSON fields before interpreting a control."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise GitHubConnectionInputError()
        result[key] = value
    return result


def _failure(error):
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


async def _admit(request, user, *, mutating=False):
    """Derive owner/lease proof from upstream auth before reading a secret body."""
    policy = request.app.state.private_access_policy
    context = await policy.authorize(request, user)
    request.state.private_browser_context = context
    if mutating:
        policy.mutation(request, context)
    return PrivateGitHubAdmission(policy, context).scope()


async def _body(request):
    """Read bounded JSON only; never echo raw payload or decode diagnostics."""
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise GitHubConnectionInputError()
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > CONNECTION_BODY_BYTES:
            raise GitHubConnectionInputError()
        body.extend(chunk)
    try:
        payload = json.loads(body, object_pairs_hook=_unique_fields)
    except (ValueError, UnicodeError):
        raise GitHubConnectionInputError() from None
    if not isinstance(payload, dict):
        raise GitHubConnectionInputError()
    return payload


def _parse(model, payload):
    """Catch validation locally so FastAPI cannot serialize credential input."""
    try:
        return model.model_validate(payload)
    except ValidationError:
        raise GitHubConnectionInputError() from None


async def _index_response(request, scope, outcome=None):
    """Capture the owner metadata revision and bind it to response release."""
    index = await request.app.state.private_github_connections.status(scope)
    request.state.github_response_binding = GitHubResponseBinding(
        owner_id=scope.owner_id, revision=index["revision"]
    )
    return JSONResponse(
        {"index": index, "outcome": outcome}, headers={"Cache-Control": "no-store"}
    )


@connection_router.get("/github-connections-capability")
async def connection_capability(request: Request):
    """Expose explicit deployment availability only, without account or owner data."""
    return JSONResponse(
        {"enabled": hasattr(request.app.state, "private_github_connections")},
        headers={"Cache-Control": "no-store"},
    )


@connection_router.get("/github-connections")
async def connection_index(request: Request, user: CurrentActiveUser):
    """Return this profile/lease's private connection metadata after live admission."""
    try:
        scope = await _admit(request, user)
        return await _index_response(request, scope)
    except Exception as error:
        return _failure(error)


@connection_router.post("/github-connections/{action}")
async def connection_action(
    action: Literal[
        "setup",
        "provision",
        "begin",
        "edit",
        "token",
        "confirm",
        "cancel",
        "refresh",
        "disconnect",
        "cleanup",
    ],
    request: Request,
    user: CurrentActiveUser,
):
    """Dispatch only the fixed private controls, with CSRF before secret ingestion."""
    try:
        scope = await _admit(request, user, mutating=True)
        payload = await _body(request)
        service = request.app.state.private_github_connections
        if action == "provision":
            if payload:
                raise GitHubConnectionInputError()
            outcome = await request.app.state.private_github_provisioner.begin(scope)
        elif action == "setup":
            data = _parse(GitHubAppSetupRequest, payload)
            outcome = await service.configure_app(
                scope, client_id=data.client_id, slug=data.slug, secret=data.secret
            )
        elif action == "begin":
            data = _parse(GitHubBrowserConnectRequest, payload)
            outcome = await service.begin(scope, data.connection_id)
        elif action == "token":
            data = _parse(GitHubTokenConnectRequest, payload)
            outcome = await service.begin_token(scope, data.token, data.connection_id)
        elif action == "edit":
            data = _parse(GitHubConnectionRequest, payload)
            outcome = await service.edit(scope, data.connection_id)
        elif action == "confirm":
            data = _parse(GitHubConsentRequest, payload)
            outcome = await service.confirm(scope, data.request_id, data.repository_ids)
        elif action == "cancel":
            data = _parse(GitHubPendingRequest, payload)
            outcome = await service.cancel(scope, data.request_id)
        elif action == "refresh":
            data = _parse(GitHubConnectionRequest, payload)
            outcome = await service.refresh(scope, data.connection_id)
        elif action == "disconnect":
            data = _parse(GitHubDisconnectRequest, payload)
            outcome = await service.disconnect(
                scope, data.connection_id, data.generation
            )
        else:
            if payload:
                raise GitHubConnectionInputError()
            outcome = await service.cleanup(scope)
        return await _index_response(request, scope, outcome)
    except Exception as error:
        return _failure(error)


@connection_router.get("/github-connections/callback")
async def connection_callback(request: Request):
    """Complete only the fixed bound return; never forward its code/state in a redirect."""
    query = {"outcome": "authorization-unconfirmed"}
    try:
        policy = request.app.state.private_access_policy
        context = await policy.callback(request)
        request.state.private_browser_context = context
        scope = PrivateGitHubAdmission(policy, context).scope()
        result = await request.app.state.private_github_connections.complete(
            scope, SecretStr(str(request.url))
        )
        query = {"outcome": "consent", "request": result["request_id"]}
    except PrivateSessionRequired:
        query = {"outcome": "signin-required"}
    except Exception:
        # A known or unknown exchange outcome never replays or chooses another
        # account. The manager reads current state and preserves existing ready rows.
        pass
    return RedirectResponse(
        "/settings/github?" + urlencode(query),
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@connection_router.get("/github-connections/app-registration/callback")
async def app_registration_callback(request: Request):
    """Store App credentials on a bound registration return, then open installation."""
    destination = "/settings/github?deployment=1&registration=unconfirmed"
    try:
        policy = request.app.state.private_access_policy
        context = await policy.callback(request, provisioning=True)
        request.state.private_browser_context = context
        scope = PrivateGitHubAdmission(policy, context).scope()
        destination = await request.app.state.private_github_provisioner.complete(
            scope, SecretStr(str(request.url))
        )
    except Exception:
        pass
    return RedirectResponse(
        destination,
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
