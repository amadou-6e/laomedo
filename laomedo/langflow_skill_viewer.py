"""Optional Langflow app factory with authenticated, read-only skill inspection.

Langflow is an optional deployment dependency, not imported by the core package.
No runner/provider credentials are used by this route.
"""
import os
from pathlib import Path

from .skill_inspection import InspectionError, inspect_skill


def install_routes(app, root: Path, authenticate):
    from fastapi import Depends, HTTPException
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    @app.get("/api/v1/laomedo/skills/{skill_id}/{revision_id}",
             dependencies=[Depends(authenticate)])
    async def read_skill(skill_id: str, revision_id: str):
        try:
            result = await run_in_threadpool(inspect_skill, root, skill_id, revision_id)
        except InspectionError as exc:
            code = str(exc)
            status = 400 if code in {"invalid_skill_id", "immutable_skill_revision_required"} else 404
            raise HTTPException(status_code=status, detail={"code": code}) from None
        return JSONResponse(result, headers={"Cache-Control": "no-store",
                                            "X-Content-Type-Options": "nosniff"})


def create_app():
    from langflow.main import create_app as upstream_app, setup_static_files
    from langflow.services.auth.utils import get_current_active_user

    root = Path(os.environ["LAOMEDO_SKILL_STORE"])
    frontend = Path(os.environ["LANGFLOW_FRONTEND_PATH"])
    app = upstream_app()
    install_routes(app, root, get_current_active_user)
    # Register the API before the installed runtime's catch-all SPA routes.
    setup_static_files(app, frontend)
    return app
