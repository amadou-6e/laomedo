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


class IssueOperationData(Component):
    display_name = 'Extract approved issue operations'
    name = 'IssueOperationData'
    icon = 'ListChecks'
    inputs = [DataInput(name='accepted', display_name='Accepted success')]
    outputs = [Output(name='modify', display_name='Update Operation', method='modify_output', group_outputs=True),
               Output(name='operations', display_name='Operations', method='operations_output', group_outputs=True)]
    def _pre_run_setup(self): self._operations = None
    def _bundle(self):
        if self._operations is None:
            route = value(self.accepted); validation = route.get('validation', {})
            envelope = validation.get('agent_submission', {})
            if (route.get('route') != 'success' or validation.get('contract_status') != 'accepted' or
                envelope.get('task_outcome') != 'success' or envelope.get('evidence_complete') is not True):
                raise ValueError('accepted_native_success_required')
            run_id = envelope.get('run_reference', {}).get('run_id')
            if not isinstance(run_id, str): raise ValueError('native_run_reference_required')
            self._operations = call('/operations', {'run_id':run_id})['operations']
        return self._operations
    def modify_output(self) -> Data: return Data(data=self._bundle()['modify'])
    def operations_output(self) -> Data: return Data(data=self._bundle())
