"""Buffered saved-account node reads; graph admission and writes stay separate."""

from typing import Literal

from fastapi import APIRouter, Request
from langflow.api.utils import CurrentActiveUser
from starlette.responses import JSONResponse

from laomedo.github.connections.models import (
    GitHubNodeReadRequest,
    GitHubResponseBinding,
)
from laomedo.integrations.langflow.authentication.connections import (
    _admit,
    _body,
    _failure,
    _parse,
)

private_node_router = APIRouter(
    prefix="/api/v1/laomedo/private-github-nodes", tags=["Private GitHub nodes"]
)


@private_node_router.post("/{action}")
async def private_node_read(
    action: Literal["discover", "inspect"], request: Request, user: CurrentActiveUser
):
    """Admit profile/lease/CSRF and bind buffered results to their live generation."""
    try:
        scope = await _admit(request, user, mutating=True)
        selected = _parse(GitHubNodeReadRequest, await _body(request))
        result = await request.app.state.private_github_nodes.read(
            scope, action=action, **selected.model_dump()
        )
        request.state.github_response_binding = GitHubResponseBinding(
            owner_id=scope.owner_id, authorization=result.authorization
        )
        return JSONResponse(result.payload, headers={"Cache-Control": "no-store"})
    except Exception as error:
        return _failure(error)
