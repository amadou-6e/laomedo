"""Implementation owned by host / runner / routes."""

from __future__ import annotations

import laomedo.host.runner.settings as _runner_settings


def install_runner_service_routes(app, authenticate, service=None):
    import laomedo.host.runner.service as _runner_service
    from fastapi import Depends
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    service = service or _runner_service.RunnerService(
        _runner_settings.Settings().service_file
    )

    async def respond(action, url):
        try:
            value = await run_in_threadpool(action, url)
        except Exception:
            raise HTTPException(
                503, detail={"code": "runner_service_configuration_unavailable"}
            ) from None
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/laomedo/runner-service", dependencies=[Depends(authenticate)])
    async def status(url: str | None = None):
        return await respond(service.status, url)

    @app.post(
        "/api/v1/laomedo/runner-service/start", dependencies=[Depends(authenticate)]
    )
    async def start(url: str | None = None):
        return await respond(service.start, url)

    @app.post(
        "/api/v1/laomedo/runner-service/cancel-start",
        dependencies=[Depends(authenticate)],
    )
    async def cancel_start(startup_id: str):
        return await respond(service.cancel_start, startup_id)
