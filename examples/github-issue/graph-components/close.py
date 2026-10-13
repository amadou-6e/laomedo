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

class CloseAfterIssueUpdate(Component):
    display_name = 'Close issue after confirmed update'
    name = 'CloseAfterIssueUpdate'
    icon = 'CircleCheck'
    inputs = [DataInput(name='update_receipt', display_name='Update receipt')]
    outputs = [Output(name='receipt', display_name='Close receipt', method='close_output')]
    def close_output(self) -> Data:
        receipt = value(self.update_receipt)
        if not isinstance(receipt, dict) or receipt.get('result', {}).get('operation', {}).get('status') != 'succeeded':
            self.stop('receipt')
            return Data(data={'status':'not_dispatched', 'error_category':'update_not_confirmed'})
        return Data(data=call('/close', {'run_id':receipt['run_id']}))
