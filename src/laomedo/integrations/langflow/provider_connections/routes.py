"""Same-origin authenticated Settings and one-use native return routes."""

import hashlib
import logging
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError
from urllib.parse import urlsplit
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import (
    GraphProviderPreferences,
    StartProviderLogin,
    DisconnectRequest,
    SaveGoConnection,
    SubmitClaudeCode,
    SubscriptionRequest,
)


def session_lease(request: Request, service) -> str:
    """Require an authenticated browser cookie, without exposing it downstream."""
    cookie = request.cookies.get("access_token_lf")
    if (
        not cookie
        or request.headers.get("authorization")
        or request.headers.get("x-api-key")
        or "x-api-key" in request.query_params
    ):
        raise HTTPException(401, detail={"code": "provider_session_required"})
    lease = service.resolve_lease(hashlib.sha256(cookie.encode()).hexdigest())
    try:
        service.check_lease(lease)
    except ProviderConnectionError:
        raise HTTPException(401, detail={"code": "provider_session_required"}) from None
    return lease


def install_provider_routes(app, service, authenticate, *, origin: str):
    """Install only in the admitted single-worker profile runtime, before the SPA."""
    prefix = "/api/v1/laomedo/provider-connections"

    async def respond(action, *args, **kwargs):
        """Project safe domain responses; raw provider errors never reach the UI."""
        try:
            value = await run_in_threadpool(action, *args, **kwargs)
            return JSONResponse(value, headers={"Cache-Control": "no-store"})
        except ProviderConnectionError as error:
            raise HTTPException(409, detail={"code": error.code}) from None
        except Exception:
            raise HTTPException(
                503, detail={"code": "provider_connections_unavailable"}
            ) from None

    @app.get(prefix)
    async def list_connections(request: Request, user=Depends(authenticate)):
        """Read only the currently authenticated profile's safe connection rows."""
        session_lease(request, service)

        def rows():
            """Serialize typed safe projections outside the event loop."""
            return {
                "connections": [
                    row.model_dump(mode="json") for row in service.list(user.id)
                ]
            }

        return await respond(rows)

    async def owned_graph(flow_id: UUID, user):
        """Require an existing graph belonging to the authenticated profile."""
        from langflow.services.database.models.flow.model import Flow
        from langflow.services.deps import session_scope
        from sqlmodel import select

        async with session_scope() as db:
            flow = (
                await db.exec(
                    select(Flow).where(Flow.id == flow_id, Flow.user_id == user.id)
                )
            ).first()
            if flow is None:
                raise HTTPException(
                    404, detail={"code": "provider_connection_unavailable"}
                )

    @app.get(prefix + "/graphs/{flow_id}")
    async def graph_preferences(
        flow_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Read only the current owner's graph-specific preference."""
        session_lease(request, service)
        await owned_graph(flow_id, user)
        return await respond(
            lambda: service.graph_preferences(user.id, flow_id).model_dump(mode="json")
        )

    @app.get(prefix + "/graphs/{flow_id}/limits/{connection_id}")
    async def cached_limits(
        flow_id: UUID,
        connection_id: UUID,
        request: Request,
        generation: int = Query(ge=1),
        user=Depends(authenticate),
    ):
        """Read only this authenticated graph owner's lease-visible cached account limits."""
        lease = session_lease(request, service)
        await owned_graph(flow_id, user)
        return await respond(
            lambda: service.subscriptions.read(
                user.id, connection_id, generation, lease
            ).model_dump(mode="json")
        )

    @app.post(prefix + "/graphs/{flow_id}/limits/{connection_id}")
    async def refresh_limits(
        flow_id: UUID,
        connection_id: UUID,
        request: Request,
        payload: SubscriptionRequest,
        user=Depends(authenticate),
    ):
        """Explicit same-origin zero-turn refresh, fenced before and after native observation."""
        lease = session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        await owned_graph(flow_id, user)
        return await respond(
            lambda: service.subscriptions.refresh(
                user.id, connection_id, payload.generation, lease
            ).model_dump(mode="json")
        )

    @app.put(prefix + "/graphs/{flow_id}")
    async def save_graph_preferences(
        flow_id: UUID,
        request: Request,
        preferences: GraphProviderPreferences,
        user=Depends(authenticate),
    ):
        """Set a graph preference through an explicit same-origin authenticated write."""
        session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        await owned_graph(flow_id, user)
        return await respond(
            lambda: service.save_graph_preferences(
                user.id, flow_id, preferences
            ).model_dump(mode="json")
        )

    @app.post(prefix + "/attempts")
    async def begin_login(request: Request, user=Depends(authenticate)):
        """Start one explicit Codex plan authorization, never on a read or mount."""
        lease = session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        try:
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 1024:
                    raise ValueError()
            payload = StartProviderLogin.model_validate_json(bytes(data))
            connection_id = payload.connection_id
        except (ValueError, TypeError, ValidationError):
            raise HTTPException(
                400, detail={"code": "provider_request_refused"}
            ) from None

        def begin():
            """Return only a native login URL and an opaque attempt receipt."""
            if payload.provider == "claude":
                return service.claude.begin(
                    user.id, lease_hash=lease, connection_id=connection_id
                )
            return service.codex.begin(
                user.id, connection_id=connection_id, lease_hash=lease
            )

        return await respond(begin)

    @app.post(prefix + "/opencode-go")
    async def save_go_connection(request: Request, user=Depends(authenticate)):
        """Admit an explicitly submitted Go key without any inference or host import."""
        lease = session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        try:
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 12288:
                    raise ValueError()
            payload = SaveGoConnection.model_validate_json(bytes(data))
        except (ValueError, TypeError, ValidationError):
            raise HTTPException(
                400, detail={"code": "provider_request_refused"}
            ) from None

        def save():
            """Project only the saved key's nonsecret metadata and duplicate result."""
            row, duplicate = service.go.save(
                user.id, payload.key, payload.label, lease_hash=lease
            )
            return {"connection": row.model_dump(mode="json"), "duplicate": duplicate}

        return await respond(save)

    @app.get(prefix + "/claude/attempts/{attempt_id}")
    async def claude_attempt(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Read only the owner's native receipt and provider-owned sign-in link."""
        lease = session_lease(request, service)
        return await respond(
            lambda: service.claude.details(user.id, attempt_id, lease_hash=lease)
        )

    @app.post(prefix + "/claude/attempts/{attempt_id}/code")
    async def claude_code(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Relay one explicit code submission into the same official native process."""
        lease = session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        try:
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 8192:
                    raise ValueError()
            payload = SubmitClaudeCode.model_validate_json(bytes(data))
        except (ValueError, TypeError, ValidationError):
            raise HTTPException(
                400, detail={"code": "provider_request_refused"}
            ) from None
        return await respond(
            lambda: service.claude.submit(
                user.id, attempt_id, payload.code, lease_hash=lease
            ).model_dump(mode="json")
        )

    @app.get(prefix + "/{connection_id}/disconnect")
    async def inspect_disconnect(
        connection_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Inspect affected runs before an explicit connection-removal confirmation."""
        session_lease(request, service)
        return await respond(
            lambda: service.disconnect_info(user.id, connection_id).model_dump(
                mode="json"
            )
        )

    @app.post(prefix + "/{connection_id}/disconnect")
    async def disconnect(
        connection_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Fence only the inspected local connection and reconcile its native cleanup."""
        session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        data = bytearray()
        try:
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 1024:
                    raise ValueError()
            payload = DisconnectRequest.model_validate_json(bytes(data))
        except (ValueError, TypeError, ValidationError):
            raise HTTPException(
                400, detail={"code": "provider_request_refused"}
            ) from None
        return await respond(
            lambda: service.disconnect(
                user.id, connection_id, payload.generation, payload.revision
            ).model_dump(mode="json")
        )

    @app.post(prefix + "/{connection_id}/cleanup")
    async def cleanup(
        connection_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Retry an already-fenced cleanup; this never reauthorizes a connection."""
        session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 2:
                raise HTTPException(403, detail={"code": "provider_request_refused"})
            body.extend(chunk)
        if body != b"{}":
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        return await respond(
            lambda: service.retry_cleanup(user.id, connection_id).model_dump(
                mode="json"
            )
        )

    @app.get(prefix + "/attempts/{attempt_id}")
    async def login_progress(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Observe a bounded attempt without replaying authorization."""
        lease = session_lease(request, service)
        return await respond(
            lambda: service.progress(user.id, attempt_id, lease_hash=lease).model_dump(
                mode="json"
            )
        )

    @app.post(prefix + "/attempts/{attempt_id}/cancel")
    async def cancel_login(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Fence a native return before navigating back to saved connections."""
        lease = session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        return await respond(
            lambda: service.cancel(user.id, attempt_id, lease_hash=lease).model_dump(
                mode="json"
            )
        )

    @app.get(prefix + "/codex/attempts/{attempt_id}")
    async def codex_attempt(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Return one-use device details only to the originating browser lease."""
        lease = session_lease(request, service)
        return await respond(
            lambda: service.codex.details(user.id, attempt_id, lease_hash=lease)
        )

    @app.post(prefix + "/codex/attempts/{attempt_id}/confirm")
    async def confirm_codex(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Explicitly confirm replacement without accepting a client-supplied identity."""
        lease = session_lease(request, service)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 2:
                raise HTTPException(400, detail={"code": "provider_request_refused"})
            data.extend(chunk)
        if data != b"{}":
            raise HTTPException(400, detail={"code": "provider_request_refused"})
        return await respond(
            lambda: service.codex.confirm(
                user.id, attempt_id, lease_hash=lease
            ).model_dump(mode="json")
        )
