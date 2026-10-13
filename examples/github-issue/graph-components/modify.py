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

class ApplyIssueProposal(Component):
    display_name = 'Apply approved issue update'
    name = 'ApplyIssueProposal'
    icon = 'Github'
    inputs = [DataInput(name='accepted', display_name='Accepted success')]
    outputs = [Output(name='receipt', display_name='Update receipt', method='apply_output')]
    def apply_output(self) -> Data:
        route = value(self.accepted)
        validation = route.get('validation', {}) if isinstance(route, dict) else {}
        envelope = validation.get('agent_submission', {})
        if (route.get('route') != 'success' or validation.get('contract_status') != 'accepted' or
            envelope.get('task_outcome') != 'success' or envelope.get('evidence_complete') is not True):
            raise ValueError('accepted_native_success_required')
        run_id = envelope.get('run_reference', {}).get('run_id')
        if not isinstance(run_id, str): raise ValueError('native_run_reference_required')
        return Data(data=call('/modify', {'run_id':run_id}))
