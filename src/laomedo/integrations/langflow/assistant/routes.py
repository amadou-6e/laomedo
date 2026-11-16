"""Authenticated assistant HTTP adapters with owner and response-release fences."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from starlette.responses import JSONResponse
from langflow.services.auth.utils import get_current_active_user

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    ConversationRequest,
    MessageRequest,
    StopRequest,
)

router = APIRouter(prefix="/api/v1/laomedo/assistant", tags=["Application assistant"])


async def access(request: Request, user=Depends(get_current_active_user)):
    """Resolve the current app profile and its validated native session."""
    runtime = request.app.state.laomedo_assistant
    try:
        key = await runtime.session(request, user)
        return runtime, UUID(str(user.id)), key
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


async def release(runtime, owner, key, result, *, status=200):
    """Recheck access after asynchronous work; no prior profile gets a late payload."""
    await runtime.check_session(owner, key)
    return JSONResponse(
        result,
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/status")
async def status(request: Request, user=Depends(get_current_active_user)):
    """Expose only feature availability without creating a runner or model request."""
    return JSONResponse(
        {"available": request.app.state.laomedo_assistant.ready, "provider": "codex"},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/models")
async def models(context=Depends(access)):
    """Discover actual model choices; inference is never part of model selection."""
    runtime, owner, key = context
    try:
        return await release(runtime, owner, key, await runtime.models(owner))
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.post("/conversations")
async def create_conversation(body: ConversationRequest, context=Depends(access)):
    """Create retained chat metadata using a supported provider and initial defaults."""
    runtime, owner, key = context
    try:
        return await release(
            runtime, owner, key, await runtime.create(owner, key, body), status=201
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.get("/conversations")
async def list_conversations(
    cursor: int = Query(default=0, ge=0, le=10000), context=Depends(access)
):
    """Read bounded owner-visible conversation summaries."""
    runtime, owner, key = context
    try:
        return await release(
            runtime, owner, key, await runtime.store.list(owner, cursor)
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.get("/conversations/{identifier}")
async def conversation_detail(
    identifier: UUID,
    cursor: int = Query(default=0, ge=0, le=10000),
    context=Depends(access),
):
    """Reopen retained history and reconcile its existing attempt without replay."""
    runtime, owner, key = context
    try:
        return await release(
            runtime, owner, key, await runtime.detail(owner, identifier, cursor)
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.post("/conversations/{identifier}/messages")
async def send_message(identifier: UUID, body: MessageRequest, context=Depends(access)):
    """Return an existing reservation for duplicates; acknowledge new background work with 202."""
    runtime, owner, key = context
    try:
        return await release(
            runtime,
            owner,
            key,
            await runtime.send(owner, key, identifier, body),
            status=202,
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.get("/conversations/{identifier}/activity")
async def activity(
    identifier: UUID,
    attempt: UUID,
    after: int = Query(default=0, ge=0, le=2147483647),
    context=Depends(access),
):
    """Read the existing normalized Activity boundary, including retained offline snapshots."""
    runtime, owner, key = context
    try:
        result = await runtime.activity(owner, identifier, attempt, after)
        # Application display metadata stays outside the common Activity page
        # and retained snapshots. No host capability or call ID is exposed.
        result = {**result, "tool_names": runtime.mcp.display_names()}
        return await release(
            runtime,
            owner,
            key,
            result,
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.post("/conversations/{identifier}/stop")
async def stop(identifier: UUID, body: StopRequest, context=Depends(access)):
    """Request cancellation of this conversation's exact active attempt."""
    runtime, owner, key = context
    try:
        return await release(
            runtime,
            owner,
            key,
            await runtime.stop(owner, identifier, body.attempt_id),
            status=202,
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@router.post("/lock")
async def lock(context=Depends(access)):
    """Revoke chat authority before the profile is locked or signed out."""
    runtime, owner, key = context
    try:
        await runtime.lock_session(key)
        return JSONResponse({"state": "locked"}, headers={"Cache-Control": "no-store"})
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None
