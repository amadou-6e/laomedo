"""Authenticated buffered private Skill routes, separate from public services."""

from typing import Literal

from fastapi import APIRouter, Request
from langflow.api.utils import CurrentActiveUser
from starlette.responses import JSONResponse

from laomedo.github.connections.models import GitHubResponseBinding
from laomedo.integrations.langflow.authentication.connections import (
    _admit,
    _body,
    _failure,
    _parse,
)
from laomedo.github.connections.skills.models import (
    PrivateSkillChoiceRequest,
    PrivateSkillCompareRequest,
    PrivateSkillHistoryRequest,
    PrivateSkillRequest,
    PrivateSkillRevisionRequest,
)

private_skill_router = APIRouter(
    prefix="/api/v1/laomedo/private-skills", tags=["Private Skills"]
)


@private_skill_router.post("/{action}")
async def private_skill_action(
    action: Literal["discover", "revisions", "inspect", "history", "compare"],
    request: Request,
    user: CurrentActiveUser,
):
    """Admit owner/session/CSRF before parsing; bind buffered bytes before release."""
    try:
        scope = await _admit(request, user, mutating=True)
        payload = await _body(request)
        service = request.app.state.private_skill_access
        if action == "discover":
            selected = _parse(PrivateSkillRequest, payload)
            result = await service.discover(
                scope, selected.connection_id, selected.repository_id
            )
        elif action == "revisions":
            selected = _parse(PrivateSkillChoiceRequest, payload)
            result = await service.revisions(
                scope, selected.connection_id, selected.repository_id, selected.choice
            )
        elif action == "inspect":
            selected = _parse(PrivateSkillRevisionRequest, payload)
            result = await service.inspect(
                scope,
                selected.connection_id,
                selected.repository_id,
                selected.skill_id,
                selected.revision_id,
            )
        elif action == "history":
            selected = _parse(PrivateSkillHistoryRequest, payload)
            result = await service.history(
                scope, selected.connection_id, selected.repository_id, selected.skill_id
            )
        else:
            selected = _parse(PrivateSkillCompareRequest, payload)
            result = await service.compare(
                scope,
                selected.connection_id,
                selected.repository_id,
                selected.skill_id,
                selected.before,
                selected.after,
            )
        request.state.github_response_binding = GitHubResponseBinding(
            owner_id=scope.owner_id, authorization=result.authorization
        )
        return JSONResponse(result.payload, headers={"Cache-Control": "no-store"})
    except Exception as error:
        return _failure(error)
