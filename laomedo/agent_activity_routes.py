"""Authenticated, owner-scoped read-only activity API."""
import os
from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .agent_activity import ActivityStore


def install_activity_routes(app, authenticate, store=None):
    def configured():
        path=os.environ.get('LAOMEDO_AGENT_ACTIVITY_DB')
        if store is None and not path:
            raise HTTPException(503,detail={'code':'agent_activity_not_configured'})
        return store if store is not None else ActivityStore(path)

    def owner(user):
        identity=getattr(user,'id',None)
        if identity is None: raise HTTPException(401)
        return str(identity)

    def response(body):
        return JSONResponse({'schema_version':'laomedo.agent-activity.v1',**body},
                            headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @app.get('/api/v1/laomedo/agent-activity/{flow}/{node}')
    async def list_runs(flow: str, node: str, user=Depends(authenticate)):
        identity=owner(user)
        result=await run_in_threadpool(configured().runs,identity,flow,node)
        return response({'runs':result})

    @app.get('/api/v1/laomedo/agent-activity/{flow}/{node}/{run}')
    async def read_run(flow: str, node: str, run: str, after: int=Query(0,ge=0),
                       limit: int=Query(100,ge=1,le=200),user=Depends(authenticate)):
        identity=owner(user)
        try:
            result=await run_in_threadpool(configured().read,identity,flow,node,run,after,limit)
        except LookupError:
            raise HTTPException(404,detail={'code':'agent_activity_not_found'}) from None
        return response(result)
