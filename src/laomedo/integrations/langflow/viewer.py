"""Optional Langflow app factory with authenticated, read-only skill inspection.

Langflow is an optional deployment dependency, not imported by the core package.
No runner/provider credentials are used by this route.
"""

from laomedo.github.contract import labels_value
from laomedo.github.contract import repository_from_url

from pathlib import Path
from laomedo.skills.inspection.errors import InspectionError
from laomedo.skills.inspection.utils import inspect_skill
from laomedo.integrations.langflow.settings import Settings


def install_routes(app, root: Path, authenticate):
    from laomedo.agents.activity.routes import install_activity_routes

    install_activity_routes(app, authenticate)
    from laomedo.host.runner.routes import install_runner_service_routes

    install_runner_service_routes(app, authenticate)
    from fastapi import Depends
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    @app.get(
        "/api/v1/laomedo/skills/{skill_id}/{revision_id}/history",
        dependencies=[Depends(authenticate)],
    )
    async def skill_history(skill_id: str, revision_id: str, before: str = ""):
        from laomedo.skills.interface.operations.client import skill_request

        try:
            await run_in_threadpool(inspect_skill, root, skill_id, revision_id)
            value = await run_in_threadpool(
                skill_request,
                "history",
                skill_id=skill_id,
                revision_id=revision_id,
                before=before,
            )
        except Exception:
            raise HTTPException(
                400, detail={"code": "skill_history_unavailable"}
            ) from None
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.get(
        "/api/v1/laomedo/skills/{skill_id}/{revision_id}/commits/{commit_id}",
        dependencies=[Depends(authenticate)],
    )
    async def skill_diff(skill_id: str, revision_id: str, commit_id: str):
        from laomedo.skills.interface.operations.client import skill_request

        try:
            await run_in_threadpool(inspect_skill, root, skill_id, revision_id)
            value = await run_in_threadpool(
                skill_request,
                "diff",
                skill_id=skill_id,
                commit_id=commit_id,
            )
        except Exception:
            raise HTTPException(
                400, detail={"code": "skill_history_unavailable"}
            ) from None
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.get(
        "/api/v1/laomedo/skills/{skill_id}/{revision_id}/compare/{commit_id}",
        dependencies=[Depends(authenticate)],
    )
    async def compare_skill(skill_id: str, revision_id: str, commit_id: str):
        from laomedo.skills.interface.operations.client import skill_request

        try:
            await run_in_threadpool(inspect_skill, root, skill_id, revision_id)
            value = await run_in_threadpool(
                skill_request,
                "compare",
                skill_id=skill_id,
                revision_id=revision_id,
                commit_id=commit_id,
            )
        except Exception:
            raise HTTPException(
                400, detail={"code": "skill_comparison_unavailable"}
            ) from None
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.get(
        "/api/v1/laomedo/skills/{skill_id}/{revision_id}",
        dependencies=[Depends(authenticate)],
    )
    async def read_skill(skill_id: str, revision_id: str):
        try:
            result = await run_in_threadpool(
                inspect_skill,
                root,
                skill_id,
                revision_id,
                include_images=True,
            )
        except InspectionError as exc:
            code = str(exc)
            status = (
                400
                if code in {"invalid_skill_id", "immutable_skill_revision_required"}
                else 404
            )
            raise HTTPException(status_code=status, detail={"code": code}) from None
        return JSONResponse(
            result,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post(
        "/api/v1/laomedo/github-issues/inspect", dependencies=[Depends(authenticate)]
    )
    async def read_issue(payload: dict):
        from laomedo.github.interface.issues.client import issue_request
        from laomedo.github.issues.contract import ERROR_CODES as ISSUE_ERROR_CODES

        try:
            if set(payload) != {"repository_url", "issue_number", "labels", "state"}:
                raise ValueError("invalid_request")
            repository_from_url(payload["repository_url"])
            labels_value(payload["labels"])
            if (
                type(payload["issue_number"]) is not int
                or not 0 < payload["issue_number"] <= 2**53 - 1
                or payload["state"] not in {"open", "closed", "all"}
            ):
                raise ValueError("selected_issue_invalid")
            result = await run_in_threadpool(
                issue_request, "execute", **payload, operation=None
            )
            issue = result.get("issue")
            if not issue or result["operation"]["status"] != "not_requested":
                raise ValueError("github_issue_unavailable")
        except Exception as exc:
            code = (
                str(exc)
                if str(exc) in ISSUE_ERROR_CODES
                else "github_issue_unavailable"
            )
            raise HTTPException(status_code=400, detail={"code": code}) from None
        return JSONResponse(
            {
                "schema_version": "laomedo.issue-inspection.v1",
                "issue": issue,
                "fetched_at": result.get("fetched_at"),
            },
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post(
        "/api/v1/laomedo/github-prs/inspect", dependencies=[Depends(authenticate)]
    )
    async def read_pr(payload: dict):
        from laomedo.github.interface.pull_requests.client import pr_request
        from laomedo.github.issues.contract import ERROR_CODES as ISSUE_ERROR_CODES
        from laomedo.github.pull_requests.contract import ERROR_CODES as PR_ERROR_CODES

        try:
            if set(payload) != {"repository_url", "pr_number", "labels", "state"}:
                raise ValueError("invalid_request")
            repository_from_url(payload["repository_url"])
            labels_value(payload["labels"])
            if (
                type(payload["pr_number"]) is not int
                or not 0 < payload["pr_number"] <= 2**53 - 1
                or payload["state"] not in {"open", "closed", "all"}
            ):
                raise ValueError("selected_pr_invalid")
            result = await run_in_threadpool(
                pr_request, "execute", **payload, operation=None
            )
            pr = result.get("pr")
            if not pr or result["operation"]["status"] != "not_requested":
                raise ValueError("github_pr_unavailable")
        except Exception as exc:
            code = str(exc) if str(exc) in PR_ERROR_CODES else "github_pr_unavailable"
            raise HTTPException(status_code=400, detail={"code": code}) from None
        return JSONResponse(
            {
                "schema_version": "laomedo.pr-inspection.v1",
                "pr": pr,
                "fetched_at": result.get("fetched_at"),
            },
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )


def create_app():
    from langflow.main import create_app as upstream_app
    from langflow.main import setup_static_files
    from langflow.services.auth.utils import get_current_active_user

    settings = Settings()
    root = Path(settings.required_path("skill_store"))
    frontend = Path(settings.required_path("frontend"))
    app = upstream_app()
    install_routes(app, root, get_current_active_user)
    # Register the API before the installed runtime's catch-all SPA routes.
    setup_static_files(app, frontend)
    return app
