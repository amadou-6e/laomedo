"""Authenticated project storage selection; model tools cannot select host roots."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.routes import access, release
from laomedo.integrations.langflow.assistant.storage.graphs import ProjectGraphs
from laomedo.integrations.langflow.assistant.storage.models import (
    RepositoryRegistration,
    RepositoryLocation,
    GraphFileRequest,
)

storage_router = APIRouter(
    prefix="/api/v1/laomedo/assistant/storage", tags=["Project storage"]
)


@storage_router.get("")
async def describe_storage(context=Depends(access)):
    runtime, owner, key = context
    try:
        result = runtime.project_storage.describe(owner)
        result["workflows"] = await ProjectGraphs(runtime).list(owner)
        return await release(runtime, owner, key, result)
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@storage_router.post("/repositories")
async def register_repository(body: RepositoryRegistration, context=Depends(access)):
    runtime, owner, key = context
    try:
        await runtime.check_session(owner, key)
        return await release(
            runtime, owner, key, runtime.project_storage.register(owner, body)
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@storage_router.post("/agent-files")
async def configure_agent_files(body: RepositoryLocation, context=Depends(access)):
    runtime, owner, key = context
    try:
        await runtime.check_session(owner, key)
        return await release(
            runtime,
            owner,
            key,
            runtime.project_storage.configure_agent_files(owner, body),
        )
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None


@storage_router.post("/graphs/{identifier}/{operation}")
async def synchronize_graph(
    identifier: UUID, operation: str, body: GraphFileRequest, context=Depends(access)
):
    runtime, owner, key = context
    if operation not in {"save", "load"}:
        raise HTTPException(404)
    try:
        result = await ProjectGraphs(runtime).sync(
            owner, key, identifier, body, load=operation == "load"
        )
        return await release(runtime, owner, key, result)
    except AssistantError as error:
        raise HTTPException(error.status, detail={"code": error.code}) from None
