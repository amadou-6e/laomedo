"""Private session readiness; upstream authentication remains the route dependency."""

from fastapi import APIRouter, Request
from langflow.api.utils import CurrentActiveUser
from starlette.responses import JSONResponse

from laomedo.integrations.langflow.authentication.errors import (
    PrivateSessionError,
    PrivateSessionRequired,
)

router = APIRouter(prefix="/api/v1/laomedo", tags=["Private browser admission"])


@router.get("/private-session")
async def private_session_status(request: Request, user: CurrentActiveUser):
    """Return readiness only; no cookie, JWT, credential or asserted owner is exposed."""
    policy = request.app.state.private_access_policy
    try:
        context = await policy.authorize(request, user)
        request.state.private_browser_context = context
        return JSONResponse(
            {"ready": True, "csrf_token": policy.csrf(context)},
            headers={"Cache-Control": "no-store"},
        )
    except PrivateSessionError as error:
        return JSONResponse(
            {"code": error.code},
            status_code=409 if isinstance(error, PrivateSessionRequired) else 503,
            headers={"Cache-Control": "no-store"},
        )
