"""Host-only controller for the bounded saved Langflow issue-operation demo."""
import argparse
import json
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
from laomedo.local_runner import LocalRunner, RunnerError, serve, _private
from laomedo.github_issue_contract import issue_digest
from laomedo.github_issue_gateway import GitHubIssueGateway
from laomedo.github_mediation import MediationStore, KnownRejected
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.host_token_connection import HostTokenConnection
from laomedo.output_contract import requirements

FORM = {"schema_version": 1, "fields": [
    {"name": "task_outcome", "type": "string", "required": True, "checks": {"enum": ["success", "failure"]}},
    {"name": "operations", "type": "object", "required": True, "checks": {"nonempty": True}}]}

def save(path, value):
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, indent=2), encoding='utf-8'); pending.replace(path)

def task(config):
    return ("Read the offered skill. This is an issue-operation proposal, not the skill's report-file task. "
            "Do not modify files or GitHub or use git/gh. Propose JSON only with task_outcome success and "
            "operations exactly as supplied. The host will check and apply it after the graph validates it. "
            "Use the output precheck tool before submitting.\nApproved operations:\n" + json.dumps(config['approved']))

def verify_record(config, record):
    if (record.get('status') != 'completed' or record.get('evidence_complete') is not True or
        record.get('completion_basis') != 'native_trace_closure' or record.get('snapshot_ready') is not True or
        record.get('requirements_revision') != requirements(FORM)['requirements_revision']):
        raise ValueError('native_evidence_not_complete')
    if json.loads(record['answer']) != {'task_outcome': 'success', 'operations': config['approved']}:
        raise ValueError('agent_plan_not_exactly_approved')

class DemoController:
    def __init__(self, root, config, engine, rest, store):
        self.root, self.config, self.engine, self.rest, self.store = root, config, engine, rest, store
        self.lock = threading.Lock()
        self.binding_path = root / 'binding.json'
        self.binding = json.loads(self.binding_path.read_text()) if self.binding_path.exists() else None
        owner = self
        class ExactTransport:
            def __call__(self, repository, operation, payload, **kwargs):
                if operation == 'issue_update':
                    number = payload['number']
                    approved = owner.config['approved']
                    changes = (approved['modify']['changes'] if number == approved['modify']['number'] else
                               {'state': 'closed'} if number == approved['close']['number'] else None)
                    original = owner.config['issues'].get(str(number))
                    if changes is None or payload['changes'] != changes or not original or payload['expected'] != issue_digest(original):
                        raise KnownRejected('campaign_effect_not_approved')
                return owner.rest(repository, operation, payload, **kwargs)
        self.gateway = GitHubIssueGateway({config['repository']: ExactTransport()}, store,
            lambda ref: self.binding if ref == config['campaign_id'] else None)

    def prepare_task(self, references):
        if self.binding_path.exists(): raise ValueError('campaign_already_entered_publication')
        if set(references) != {'modify', 'close'}: raise ValueError('issue_reference_mismatch')
        for action, issue in references.items():
            number = self.config['approved'][action]['number']
            original = self.config['issues'][str(number)]
            if not isinstance(issue, dict) or issue_digest(issue) != issue_digest(original):
                raise ValueError('issue_changed_since_campaign_preparation')
        return {'task': task(self.config)}

    def apply(self, action, run_id):
        if action not in {'modify', 'close'} or not isinstance(run_id, str): raise ValueError('invalid_operation')
        with self.lock:
            record = self.engine.status(run_id); verify_record(self.config, record)
            if self.binding is None:
                if action != 'modify': raise ValueError('update_not_confirmed')
                for number, issue in self.config['issues'].items():
                    if issue_digest(self.rest(self.config['repository'], 'issue_read', {'number': int(number)})) != issue_digest(issue):
                        raise ValueError('issue_changed_since_campaign_preparation')
                _, token = self.store.issue(run_id=run_id, invocation_id=self.config['campaign_id'],
                    repository=self.config['repository'], operations={'issue_update'},
                    target_issues={int(n) for n in self.config['issues']}, ttl_seconds=60,
                    connection_id='issue-graph-demo', connection_generation=1)
                self.binding = {'token': token, 'run_id': run_id, 'repository': self.config['repository']}
                save(self.binding_path, self.binding)
            if self.binding['run_id'] != run_id: raise ValueError('campaign_run_rebinding_denied')
            receipt_path = self.root / 'update-receipt.json'
            if action == 'close':
                if not receipt_path.exists(): raise ValueError('update_not_confirmed')
                receipt = json.loads(receipt_path.read_text())
                if receipt['run_id'] != run_id or receipt['result']['operation']['status'] != 'succeeded':
                    raise ValueError('update_not_confirmed')
            number = self.config['approved'][action]['number']
            operation = {'action': action, 'request_id': self.config['campaign_id'] + '-' + str(number),
                         'grant_ref': self.config['campaign_id']}
            if action == 'modify': operation['changes'] = self.config['approved']['modify']['changes']
            try:
                result = self.gateway.execute('https://github.com/' + self.config['repository'], [], 'all', number, operation)
                receipt = {'run_id': run_id, 'result': result}
                save(self.root / ('update-receipt.json' if action == 'modify' else 'close-receipt.json'), receipt)
                return receipt
            finally:
                if action == 'close' or 'result' not in locals() or result['operation']['status'] != 'succeeded':
                    self.store.revoke_run(run_id)

class BoundedRunner(LocalRunner):
    def bind(self, config, root): self.demo_config, self.demo_root = config, root
    def start_async(self, body, **kwargs):
        c = self.demo_config
        if (self.demo_root / 'binding.json').exists(): raise RunnerError('experiment_request_binding_denied')
        allowed = {'request_id', 'task', 'model', 'effort', 'skill_ref', 'output_requirements', 'output_retries'}
        if (set(body) != allowed or body['task'] != task(c) or body['model'] != 'gpt-6-luna' or body['effort'] != 'low' or
            body['skill_ref'] != c['skill'] or body['output_requirements'] != requirements(FORM) or body['output_retries'] != 0):
            raise RunnerError('experiment_request_binding_denied')
        return super().start_async(body, **kwargs)
    def start(self, body): raise RunnerError('experiment_request_binding_denied')
    def resume(self, *args, **kwargs): raise RunnerError('experiment_request_binding_denied')

SAFE_ERRORS = {'campaign_already_entered_publication', 'issue_reference_mismatch',
 'issue_changed_since_campaign_preparation', 'native_evidence_not_complete', 'agent_plan_not_exactly_approved',
 'update_not_confirmed', 'invalid_operation', 'campaign_run_rebinding_denied', 'invalid_request'}

def service(controller, token, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def reply(self, code, value):
            data = json.dumps(value).encode(); self.send_response(code)
            self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.reply(401, {'error_category': 'unauthorized'}); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024*1024 or self.headers.get('Content-Type') != 'application/json': raise ValueError('invalid_request')
                body = json.loads(self.rfile.read(size))
                if self.path == '/prepare' and isinstance(body, dict) and set(body) == {'modify', 'close'}:
                    result = controller.prepare_task(body)
                elif self.path in {'/modify', '/close'} and isinstance(body, dict) and set(body) == {'run_id'}:
                    result = controller.apply(self.path[1:], body['run_id'])
                else: raise ValueError('invalid_request')
                self.reply(200, result)
            except Exception as exc:
                code = str(exc) if str(exc) in SAFE_ERRORS else 'operation_state_unknown'
                self.reply(409, {'error_category': code})
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)

def main():
    p = argparse.ArgumentParser(); p.add_argument('--state', type=Path, required=True)
    p.add_argument('--token-file', type=Path, required=True); p.add_argument('--runner-port', type=int, default=8784)
    p.add_argument('--operation-port', type=int, default=8785); args = p.parse_args()
    root = _private(args.state); config = json.loads((root/'config.json').read_text())
    engine = BoundedRunner(root/'runner', Path(config['registry']), Path(config['source']),
        max_model_turns=4, lease_service=root/'lease', supervise_containers=True)
    engine.bind(config, root); engine.api_token = args.token_file.read_text().strip()
    provider = HostTokenConnection(connection_id='issue-graph-demo', generation=1, repository=config['repository'],
        token_file=Path('C:/CodeWorkspace/agentviz/.env'), key='GH_LAOMEDO', forbidden_mount=Path(config['source']))
    rest = GitHubRestTransport(config['repository'], lambda connection_id=None, connection_generation=None: provider.token('issue-graph-demo', 1))
    controller = DemoController(root, config, engine, rest, MediationStore(root/'issues.sqlite', connection_is_current=provider.current))
    threading.Thread(target=serve(engine, port=args.runner_port).serve_forever, daemon=True).start()
    service(controller, engine.api_token, args.operation_port).serve_forever()
if __name__ == '__main__': main()
