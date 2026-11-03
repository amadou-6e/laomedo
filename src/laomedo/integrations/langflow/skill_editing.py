"""Authenticated viewer writes; service capabilities never reach the browser."""

from laomedo.skills.interface.operations.client import skill_request
from laomedo.skills.operations.contract import MANUAL_ERROR_CODES
from urllib.parse import urlsplit


def install_skill_editing_routes(app, authenticate):
    """Register explicit manual actions before the SPA catch-all, default denied by the host."""
    from fastapi import Depends, HTTPException, Request
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    @app.post(
        "/api/v1/laomedo/skills/manual/{action}", dependencies=[Depends(authenticate)]
    )
    async def manual_skill_action(action: str, request: Request):
        if action not in {"editor", "save", "publish"}:
            raise HTTPException(404, detail={"code": "skill_manual_invalid"})
        origin = request.headers.get("origin")
        base = urlsplit(str(request.base_url))
        if origin and origin.rstrip("/") != f"{base.scheme}://{base.netloc}":
            raise HTTPException(403, detail={"code": "skill_manual_not_authorized"})
        body = await request.body()
        if len(body) > 4 * 1024 * 1024:
            raise HTTPException(413, detail={"code": "skill_manual_invalid"})
        try:
            import json

            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("skill_manual_invalid")
            value = await run_in_threadpool(skill_request, action, **payload)
        except Exception as exc:
            code = (
                str(exc)
                if str(exc) in MANUAL_ERROR_CODES
                else "skill_manual_unavailable"
            )
            raise HTTPException(400, detail={"code": code}) from None
        return JSONResponse(
            value,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
