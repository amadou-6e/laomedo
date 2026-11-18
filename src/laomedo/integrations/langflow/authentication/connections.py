"""Private browser connection routes; credentials never pass public service adapters."""

from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from langflow.api.utils import CurrentActiveUser
from pydantic import SecretStr
from starlette.responses import JSONResponse, RedirectResponse

from laomedo.github.connections.errors import (
    GitHubConnectionAttemptExpired,
    GitHubConnectionInputError,
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
from laomedo.integrations.langflow.authentication.errors import PrivateSessionRequired
from laomedo.integrations.langflow.authentication.policy import PrivateGitHubAdmission
from laomedo.integrations.langflow.authentication.private_requests import (
    admit_private_request,
    parse_private_payload,
    private_failure_response,
    read_private_json,
)

connection_router = APIRouter(
    prefix="/api/v1/laomedo", tags=["Private GitHub connections"]
)


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
        scope = await admit_private_request(request, user)
        return await _index_response(request, scope)
    except Exception as error:
        return private_failure_response(error)


@connection_router.post("/github-connections/{action}")
async def connection_action(
    action: Literal[
        "setup",
        "provision",
        "begin",
        "edit",
        "inventory",
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
        scope = await admit_private_request(request, user, mutating=True)
        payload = await read_private_json(request)
        service = request.app.state.private_github_connections
        if action == "provision":
            if payload:
                raise GitHubConnectionInputError()
            outcome = await request.app.state.private_github_provisioner.begin(scope)
        elif action == "setup":
            data = parse_private_payload(GitHubAppSetupRequest, payload)
            outcome = await service.configure_app(
                scope, client_id=data.client_id, slug=data.slug, secret=data.secret
            )
        elif action == "begin":
            data = parse_private_payload(GitHubBrowserConnectRequest, payload)
            outcome = await service.begin(scope, data.connection_id, app_id=data.app_id)
        elif action == "token":
            data = parse_private_payload(GitHubTokenConnectRequest, payload)
            outcome = await service.begin_token(scope, data.token, data.connection_id)
        elif action == "edit":
            data = parse_private_payload(GitHubConnectionRequest, payload)
            outcome = await service.edit(scope, data.connection_id)
        elif action == "inventory":
            data = parse_private_payload(GitHubPendingRequest, payload)
            outcome = await service.inspect_inventory(scope, data.request_id)
        elif action == "confirm":
            data = parse_private_payload(GitHubConsentRequest, payload)
            outcome = await service.confirm(scope, data.request_id, data.repository_ids)
        elif action == "cancel":
            data = parse_private_payload(GitHubPendingRequest, payload)
            outcome = await service.cancel(scope, data.request_id)
        elif action == "refresh":
            data = parse_private_payload(GitHubConnectionRequest, payload)
            outcome = await service.refresh(scope, data.connection_id)
        elif action == "disconnect":
            data = parse_private_payload(GitHubDisconnectRequest, payload)
            outcome = await service.disconnect(
                scope, data.connection_id, data.generation
            )
        else:
            if payload:
                raise GitHubConnectionInputError()
            outcome = await service.cleanup(scope)
        return await _index_response(request, scope, outcome)
    except Exception as error:
        return private_failure_response(error)


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
    except GitHubConnectionAttemptExpired:
        query = {"outcome": "signin-expired"}
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
    destination = "/settings/github?registration=unconfirmed"
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
