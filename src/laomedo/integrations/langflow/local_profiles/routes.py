"""Safe local-profile endpoints, registered only by the opt-in profile runtime."""

from fastapi import APIRouter, Request
from pydantic import ValidationError
from starlette.responses import JSONResponse

from laomedo.integrations.langflow.local_profiles.errors import ProfileError
from laomedo.integrations.langflow.local_profiles.models import ProfileCreateRequest

router = APIRouter(prefix="/api/v1/laomedo/profiles", tags=["Local profiles"])


@router.get("")
async def list_profiles(request: Request):
    try:
        result = await request.app.state.local_profile_registry.list_profiles()
        return JSONResponse(
            result.model_dump(mode="json"), headers={"Cache-Control": "no-store"}
        )
    except ProfileError as error:
        return JSONResponse(
            {"code": error.code}, status_code=503, headers={"Cache-Control": "no-store"}
        )


@router.post("")
async def create_profile(request: Request):
    try:
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 4096:
                raise ProfileError("profile_input_invalid")
        try:
            payload = ProfileCreateRequest.model_validate_json(bytes(data))
        except ValidationError as error:
            safe_errors = error.errors(include_input=False, include_context=False)
            if any(
                issue["type"] == "profile_name_unavailable" for issue in safe_errors
            ):
                raise ProfileError("profile_name_unavailable") from None
            raise ProfileError("profile_input_invalid") from None
        result = await request.app.state.local_profile_registry.create_profile(payload)
        return JSONResponse(
            result.model_dump(mode="json"),
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )
    except ProfileError as error:
        status = (
            400
            if error.code == "profile_input_invalid"
            else 409 if error.code == "profile_name_unavailable" else 503
        )
        return JSONResponse(
            {"code": error.code},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )


async def profile_mode(request: Request):
    """Non-secret capability flag; existing previews retain their normal login UI."""
    return JSONResponse(
        {"enabled": getattr(request.app.state, "local_profiles_enabled", False)},
        headers={"Cache-Control": "no-store"},
    )
