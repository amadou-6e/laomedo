"""Optional Langflow app factory with authenticated, read-only skill inspection.

Langflow is an optional deployment dependency, not imported by the core package.
No runner/provider credentials are used by this route.
"""

from pathlib import Path
import laomedo.skills.inspection.errors as _inspection_errors
import laomedo.skills.inspection.utils as _inspection_utils
import laomedo.integrations.langflow.settings as _langflow_settings


def install_routes(app, root: Path, authenticate):
    import laomedo.activity.agent_activity.routes as _agent_activity_routes

    _agent_activity_routes.install_activity_routes(app, authenticate)
    import laomedo.host.runner.routes as _runner_routes

    _runner_routes.install_runner_service_routes(app, authenticate)
    from fastapi import Depends
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    @app.get(
        "/api/v1/laomedo/skills/{skill_id}/{revision_id}/history",
        dependencies=[Depends(authenticate)],
    )
    async def skill_history(skill_id: str, revision_id: str, before: str = ""):
        import laomedo.skills.operations.client as _operations_client

        try:
            await run_in_threadpool(
                _inspection_utils.inspect_skill, root, skill_id, revision_id
            )
            value = await run_in_threadpool(
                _operations_client.skill_request,
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
        import laomedo.skills.operations.client as _operations_client

        try:
            await run_in_threadpool(
                _inspection_utils.inspect_skill, root, skill_id, revision_id
            )
            value = await run_in_threadpool(
                _operations_client.skill_request,
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
        import laomedo.skills.operations.client as _operations_client

        try:
            await run_in_threadpool(
                _inspection_utils.inspect_skill, root, skill_id, revision_id
            )
            value = await run_in_threadpool(
                _operations_client.skill_request,
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
                _inspection_utils.inspect_skill,
                root,
                skill_id,
                revision_id,
                include_images=True,
            )
        except _inspection_errors.InspectionError as exc:
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
        import laomedo.github.issues.client as _issues_client
        import laomedo.github.issues.contract as _issues_contract

        try:
            if set(payload) != {"repository_url", "issue_number", "labels", "state"}:
                raise ValueError("invalid_request")
            _issues_contract.repository_from_url(payload["repository_url"])
            _issues_contract.labels_value(payload["labels"])
            if (
                type(payload["issue_number"]) is not int
                or not 0 < payload["issue_number"] <= 2**53 - 1
                or payload["state"] not in {"open", "closed", "all"}
            ):
                raise ValueError("selected_issue_invalid")
            result = await run_in_threadpool(
                _issues_client.issue_request, "execute", **payload, operation=None
            )
            issue = result.get("issue")
            if not issue or result["operation"]["status"] != "not_requested":
                raise ValueError("github_issue_unavailable")
        except Exception as exc:
            code = (
                str(exc)
                if str(exc) in _issues_contract.ERROR_CODES
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
        import laomedo.github.pull_requests.client as _pull_requests_client
        import laomedo.github.issues.contract as _issues_contract
        import laomedo.github.pull_requests.contract as _pull_requests_contract

        try:
            if set(payload) != {"repository_url", "pr_number", "labels", "state"}:
                raise ValueError("invalid_request")
            _issues_contract.repository_from_url(payload["repository_url"])
            _issues_contract.labels_value(payload["labels"])
            if (
                type(payload["pr_number"]) is not int
                or not 0 < payload["pr_number"] <= 2**53 - 1
                or payload["state"] not in {"open", "closed", "all"}
            ):
                raise ValueError("selected_pr_invalid")
            result = await run_in_threadpool(
                _pull_requests_client.pr_request, "execute", **payload, operation=None
            )
            pr = result.get("pr")
            if not pr or result["operation"]["status"] != "not_requested":
                raise ValueError("github_pr_unavailable")
        except Exception as exc:
            code = (
                str(exc)
                if str(exc) in _pull_requests_contract.ERROR_CODES
                else "github_pr_unavailable"
            )
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

    settings = _langflow_settings.Settings()
    root = Path(settings.required_path("skill_store"))
    frontend = Path(settings.required_path("frontend"))
    app = upstream_app()
    install_routes(app, root, get_current_active_user)
    # Register the API before the installed runtime's catch-all SPA routes.
    setup_static_files(app, frontend)
    return app
