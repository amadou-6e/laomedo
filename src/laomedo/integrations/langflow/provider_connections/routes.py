"""Same-origin authenticated Settings and one-use native return routes."""

import hashlib
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from pydantic import ValidationError
from urllib.parse import urlsplit
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse

from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.models import (
    StartProviderLogin,
    DisconnectRequest,
)


def session_lease(request: Request) -> str:
    """Require an authenticated browser cookie, without exposing it downstream."""
    cookie = request.cookies.get("access_token_lf")
    if (
        not cookie
        or request.headers.get("authorization")
        or request.headers.get("x-api-key")
        or "x-api-key" in request.query_params
    ):
        raise HTTPException(401, detail={"code": "provider_session_required"})
    return hashlib.sha256(cookie.encode()).hexdigest()


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
        session_lease(request)

        def rows():
            """Serialize typed safe projections outside the event loop."""
            return {
                "connections": [
                    row.model_dump(mode="json") for row in service.list(user.id)
                ]
            }

        return await respond(rows)

    @app.post(prefix + "/attempts")
    async def begin_login(request: Request, user=Depends(authenticate)):
        """Start one explicit Codex plan authorization, never on a read or mount."""
        lease = session_lease(request)
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
            progress, url = service.begin(
                user.id, origin + "/auth/callback", connection_id, lease_hash=lease
            )
            return {
                "progress": progress.model_dump(mode="json"),
                "authorization_url": url,
            }

        return await respond(begin)

    @app.get(prefix + "/{connection_id}/disconnect")
    async def inspect_disconnect(
        connection_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Inspect affected runs before an explicit connection-removal confirmation."""
        session_lease(request)
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
        session_lease(request)
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
        session_lease(request)
        if request.headers.get("origin") != origin or await request.body() != b"{}":
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
        session_lease(request)
        return await respond(
            lambda: service.progress(user.id, attempt_id).model_dump(mode="json")
        )

    @app.post(prefix + "/attempts/{attempt_id}/cancel")
    async def cancel_login(
        attempt_id: UUID, request: Request, user=Depends(authenticate)
    ):
        """Fence a native return before navigating back to saved connections."""
        session_lease(request)
        if request.headers.get("origin") != origin:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        return await respond(
            lambda: service.cancel(user.id, attempt_id).model_dump(mode="json")
        )

    @app.get("/auth/callback")
    async def login_callback(request: Request, user=Depends(authenticate)):
        """Validate a native top-level return and remove its query from the UI."""
        if request.headers.get("host") != urlsplit(origin).netloc:
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        lease = session_lease(request)
        query = request.query_params
        if len(query) > 12 or any(
            len(query.getlist(key)) != 1 or len(query[key]) > 8192 for key in query
        ):
            return RedirectResponse(
                "/settings/providers?login=failed",
                status_code=303,
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )
        try:
            result = await run_in_threadpool(
                service.complete, user.id, dict(query), lease_hash=lease
            )
            target = "/settings/providers?attempt=" + str(result.attempt_id)
        except ProviderConnectionError:
            target = "/settings/providers?login=failed"
        except Exception:
            target = "/settings/providers?login=unconfirmed"
        return RedirectResponse(
            target,
            status_code=303,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
