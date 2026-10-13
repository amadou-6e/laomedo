"""Backend-only read proxy to explicitly configured inspection connections."""
import json
import os
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
from .skill_source_client import NoRedirect
from .agent_inspection import run_id

def inspection_request(runner_url, selected=None, after=0):
    allowed=json.loads(os.environ.get('LAOMEDO_AGENT_INSPECTION_URLS','[]'))
    url=urlsplit(runner_url)
    if (not isinstance(allowed,list) or runner_url not in allowed or url.scheme!='http' or
        url.hostname not in {'127.0.0.1','localhost','host.docker.internal'} or url.path or url.query or url.fragment or url.username or url.password):
        raise ValueError('inspection_connection_unavailable')
    if type(after) is not int or not 0<=after<=1000000:raise ValueError('invalid_inspection_cursor')
    suffix='/v1/inspection/runs' if selected is None else '/v1/runs/'+run_id(selected)+'/inspection/'+str(after)
    try:
        token=Path(os.environ.get('LAOMEDO_RUNNER_TOKEN_FILE','/run/secrets/laomedo-runner-token')).read_text().strip()
        with request.build_opener(NoRedirect()).open(request.Request(runner_url+suffix,headers={'Authorization':'Bearer '+token}),timeout=10) as response:
            raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError()
        result=json.loads(raw)
        expected='laomedo.agent-history.v1' if selected is None else 'laomedo.agent-inspection.v1'
        if not isinstance(result,dict) or result.get('schema_version')!=expected:raise ValueError()
        if selected is not None and result.get('summary',{}).get('run_id')!=selected:raise ValueError()
        return result
    except Exception:raise ValueError('inspection_unavailable') from None
