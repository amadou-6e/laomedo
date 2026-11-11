"""Experiment-only safe state tracing around the unmodified launch command."""
import json
import runpy
import time
from laomedo.host.runner.service import RunnerService

original_status = RunnerService.status
original_start = RunnerService.start

def record(kind, result, started):
    print("RECOVERY_TRACE " + json.dumps({"kind":kind,"at":time.time(),"seconds":round(time.monotonic()-started,3),"result":{k:v for k,v in result.items() if k in {"state","reason","runner_state","can_start","startup_cancelled"}}}),flush=True)

def traced_status(self, *args, **kwargs):
    started=time.monotonic()
    result=original_status(self,*args,**kwargs)
    record("status",result,started)
    return result

def traced_start(self, *args, **kwargs):
    started=time.monotonic()
    result=original_start(self,*args,**kwargs)
    record("start",result,started)
    return result

RunnerService.status=traced_status
RunnerService.start=traced_start
runpy.run_module("laomedo.integrations.langflow.launch.cli",run_name="__main__")
