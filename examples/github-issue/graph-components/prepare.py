from pathlib import Path
import os
import json
from urllib import request
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema import Data, Message
class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_): return None

def call(path, body):
    token = Path(os.environ.get('LAOMEDO_RUNNER_TOKEN_FILE', '/run/secrets/laomedo-runner-token')).read_text().strip()
    req = request.Request('http://host.docker.internal:8785' + path,
        data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=90) as response:
            raw = response.read(1024*1024+1)
            if len(raw)>1024*1024: raise ValueError()
            return json.loads(raw)
    except Exception:
        raise ValueError('issue_graph_demo_operation_unavailable') from None

def value(item): return getattr(item, 'data', item)

class IssueOperationTask(Component):
    display_name = 'Prepare issue operation task'
    name = 'IssueOperationTask'
    icon = 'ListChecks'
    inputs = [DataInput(name='modify_issue', display_name='Update target'), DataInput(name='close_issue', display_name='Close target')]
    outputs = [Output(name='task', display_name='Task', method='task_output')]
    def task_output(self) -> Message:
        result = call('/prepare', {'modify':value(self.modify_issue), 'close':value(self.close_issue)})
        return Message(text=result['task'])
