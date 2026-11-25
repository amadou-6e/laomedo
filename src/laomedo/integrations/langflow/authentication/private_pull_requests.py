"""Authenticated account-scoped pull request reads."""

from typing import Literal
from fastapi import APIRouter, Request
from langflow.api.utils import CurrentActiveUser
from starlette.responses import JSONResponse
from laomedo.github.connections.models import GitHubResponseBinding
from laomedo.github.connections.pull_requests.models import (
    PrivatePullRequestRead,
    PrivatePullRequestSelection,
)
from laomedo.integrations.langflow.authentication.connections import (
    _admit,
    _body,
    _failure,
    _parse,
)

private_pull_request_router = APIRouter(
    prefix="/api/v1/laomedo/private-pull-requests", tags=["Private pull requests"]
)


@private_pull_request_router.post("/{action}")
async def private_pull_request_action(
    action: Literal["discover", "read"], request: Request, user: CurrentActiveUser
):
    """Revalidate the selected account and repository before releasing private PRs."""
    try:
        scope = await _admit(request, user, mutating=True)
        payload = await _body(request)
        service = request.app.state.private_pull_request_access
        if action == "discover":
            selected = _parse(PrivatePullRequestSelection, payload)
            result = await service.discover(
                scope, selected.connection_id, selected.repository_id
            )
        else:
            selected = _parse(PrivatePullRequestRead, payload)
            result = await service.read(
                scope,
                selected.connection_id,
                selected.repository_id,
                selected.pr_number,
            )
        request.state.github_response_binding = GitHubResponseBinding(
            owner_id=scope.owner_id, authorization=result.authorization
        )
        return JSONResponse(result.payload, headers={"Cache-Control": "no-store"})
    except Exception as error:
        return _failure(error)
