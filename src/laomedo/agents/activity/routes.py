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
    def configured():
        path = Settings().database
        if store is None and not path:
            raise HTTPException(503, detail={"code": "agent_activity_not_configured"})
        if store is None and not Path(path).is_file():
            raise HTTPException(
                503, detail={"code": "agent_activity_capture_not_started"}
            )
        return store if store is not None else ActivityStore(path, read_only=True)

    def owner(user):
        identity = getattr(user, "id", None)
        if identity is None:
            raise HTTPException(401)
        return str(identity)

    def response(body):
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
        identity = owner(user)
        result = await run_in_threadpool(
            configured().graph_runs, identity, flow, execution
        )
        return response({"runs": result})

    @app.get("/api/v1/laomedo/agent-executions/{flow}/{node}/{run}")
    async def invocation(flow: str, node: str, run: str, user=Depends(authenticate)):
        from laomedo.agents.activity.projection import project

        identity = owner(user)

        def load():
            store = configured()
            events = []
            after = 0
            while True:
                page = store.read(identity, flow, node, run, after, 200)
                events.extend(page["events"])
                after = page["next_after"]
                if not page["has_more"] or len(events) >= 20000:
                    projection = project(
                        events,
                        root_thread=page["run"]["native_session"],
                        model=page["run"]["model"],
                    )
                    if (
                        page["has_more"]
                        or page["run"].get("reason") == "invocation_boundary_unverified"
                    ):
                        projection["usage"] = None
                        projection["usage_by_thread"] = {}
                        projection["turns"] = [
                            {**turn, "usage": None, "cost": {"amount": None}}
                            for turn in projection["turns"]
                        ]
                        projection["usage_points"] = []
                        projection["cost"] = {
                            **projection["cost"],
                            "amount": None,
                            "per_thread": {},
                            "reason": (
                                "Detail limit reached."
                                if page["has_more"]
                                else "Invocation boundary is unverified."
                            ),
                        }
                        projection["cost_reason"] = (
                            "Detail limit reached; complete token and cost totals are unavailable."
                            if page["has_more"]
                            else "Invocation boundary is unverified; retained receipts are partial evidence."
                        )
                    return {
                        **page,
                        "run": {**page["run"], "node": node},
                        "events": events,
                        "projection": projection,
                        "truncated": page["has_more"],
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
