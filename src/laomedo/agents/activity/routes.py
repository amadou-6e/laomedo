"""Authenticated, owner-scoped read-only activity API."""

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi.responses import JSONResponse
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from laomedo.agents.activity.store import ActivityStore
from laomedo.agents.activity.settings import Settings


def install_activity_routes(app, authenticate, store=None):
    """Register authenticated read-only Activity routes; every lookup remains owner and invocation scoped."""

    def configured():
        """Open only the configured Activity store; missing configuration maps to a safe HTTP refusal."""
        path = Settings().database
        if store is None and not path:
            raise HTTPException(503, detail={"code": "agent_activity_not_configured"})
        if store is None and not Path(path).is_file():
            raise HTTPException(
                503, detail={"code": "agent_activity_capture_not_started"}
            )
        return store if store is not None else ActivityStore(path, read_only=True)

    def owner(user):
        """Extract authenticated caller identity or refuse before reading retained Activity."""
        identity = getattr(user, "id", None)
        if identity is None:
            raise HTTPException(401)
        return str(identity)

    def response(body):
        """Project the existing Activity schema with no-store and content-type protections."""
        return JSONResponse(
            {"schema_version": "laomedo.agent-activity.v1", **body},
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/v1/laomedo/agent-executions/{flow}")
    async def graph_runs(
        flow: str,
        execution: str | None = Query(None, max_length=200),
        user=Depends(authenticate),
    ):
        """Read owner-scoped invocation summaries for the selected flow/execution without native dispatch."""
        identity = owner(user)
        result = await run_in_threadpool(
            configured().graph_runs, identity, flow, execution
        )
        return response({"runs": result})

    @app.get("/api/v1/laomedo/agent-executions/{flow}/{node}/{run}")
    async def invocation(flow: str, node: str, run: str, user=Depends(authenticate)):
        """Read one owner-scoped invocation and project its bounded retained observations."""
        from laomedo.agents.activity.projection import project

        identity = owner(user)

        def load():
            """Read retained evidence and apply the selected owner-scoped projection without native execution."""
            store = configured()
            page = store.read(identity, flow, node, run, 0, 200)
            projection = project(page["events"])
            reason = page["run"].get("reason")
            if reason in {
                "invocation_boundary_unverified",
                "activity_projection_limit",
            }:
                projection["usage"] = None
                projection["usage_by_thread"] = {}
                projection["turns"] = [
                    {**turn, "usage": None, "cost": {"amount": None}}
                    for turn in projection["turns"]
                ]
                projection["usage_points"] = []
                detail = (
                    "Activity capture limit reached."
                    if reason == "activity_projection_limit"
                    else "Invocation boundary is unverified."
                )
                projection["cost"] = {
                    **projection["cost"],
                    "amount": None,
                    "per_thread": {},
                    "reason": detail,
                }
                projection["cost_reason"] = (
                    "Activity capture limit reached; complete token and cost totals are unavailable."
                    if reason == "activity_projection_limit"
                    else "Invocation boundary is unverified; retained receipts are partial evidence."
                )
            return {
                **page,
                "run": {**page["run"], "node": node},
                "events": [],
                "has_more": False,
                "projection": projection,
                "truncated": False,
            }

        try:
            result = await run_in_threadpool(load)
        except LookupError:
            raise HTTPException(
                404, detail={"code": "agent_activity_not_found"}
            ) from None
        return response(result)

    @app.get("/api/v1/laomedo/agent-activity/{flow}/{node}")
    async def list_runs(flow: str, node: str, user=Depends(authenticate)):
        """List only authenticated owner-visible Activity invocations without dispatching work."""
        identity = owner(user)
        result = await run_in_threadpool(configured().runs, identity, flow, node)
        return response({"runs": result})

    @app.get("/api/v1/laomedo/agent-activity/{flow}/{node}/{run}")
    async def read_run(
        flow: str,
        node: str,
        run: str,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=200),
        user=Depends(authenticate),
    ):
        """Read bounded owner-scoped receipts after the requested cursor; never execute native content."""
        identity = owner(user)
        try:
            result = await run_in_threadpool(
                configured().read, identity, flow, node, run, after, limit
            )
        except LookupError:
            raise HTTPException(
                404, detail={"code": "agent_activity_not_found"}
            ) from None
        return response(result)
