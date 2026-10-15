"""Authenticated, owner-scoped read-only activity API."""
import os
from pathlib import Path
from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .agent_activity import ActivityStore


def install_activity_routes(app, authenticate, store=None):
    def configured():
        path=os.environ.get('LAOMEDO_AGENT_ACTIVITY_DB')
        if store is None and not path:
            raise HTTPException(503,detail={'code':'agent_activity_not_configured'})
        if store is None and not Path(path).is_file():
            raise HTTPException(503,detail={'code':'agent_activity_capture_not_started'})
        return store if store is not None else ActivityStore(path,read_only=True)

    def owner(user):
        identity=getattr(user,'id',None)
        if identity is None: raise HTTPException(401)
        return str(identity)

    def response(body):
        return JSONResponse({'schema_version':'laomedo.agent-activity.v1',**body},
                            headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @app.get('/api/v1/laomedo/agent-executions/{flow}')
    async def graph_runs(flow: str, execution: str | None=Query(None,max_length=200),user=Depends(authenticate)):
        identity=owner(user)
        result=await run_in_threadpool(configured().graph_runs,identity,flow,execution)
        return response({'runs':result})

    @app.get('/api/v1/laomedo/agent-executions/{flow}/{node}/{run}')
    async def invocation(flow: str,node: str,run: str,user=Depends(authenticate)):
        from .agent_activity_projection import project
        identity=owner(user)
        def load():
            store=configured()
            events=[]
            after=0
            while True:
                page=store.read(identity,flow,node,run,after,200)
                events.extend(page['events'])
                after=page['next_after']
                if not page['has_more'] or len(events)>=20000:
                    return {**page,'run':{**page['run'],'node':node},'events':events,'projection':project(events,
                            root_thread=page['run']['native_session'],model=page['run']['model']),
                            'truncated':page['has_more']}
        try:
            result=await run_in_threadpool(load)
        except LookupError:
            raise HTTPException(404,detail={'code':'agent_activity_not_found'}) from None
        return response(result)

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
