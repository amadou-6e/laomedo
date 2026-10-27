"""Export only closed-schema recovery evidence; never copy answers or tokens."""
from hashlib import sha256
import json
from pathlib import Path
import socket
import sqlite3
from contextlib import closing

from laomedo.agents.output_contract import precheck_response
from laomedo.host.credentials.siwc_auth import _outside_git


def observe(root):
    root = _outside_git(root)
    config = json.loads((root / 'config.json').read_bytes())
    activation = json.loads((root / 'activation.json').read_bytes())
    ledger = json.loads((root / 'runner/turn-ledger.json').read_bytes())
    assert ledger == {'attempted_turns': 5, 'max_authorized_turns': 10}
    inputs = json.loads((root / 'flow-input/inputs.json').read_bytes())
    hashes = {sha256(json.dumps({'task': task, 'frozen_issue': inputs['snapshot']},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest(): case
        for case, task in inputs['tasks'].items()}
    leases = {}
    for supervisor in ('lease', 'nonpublishing-lease'):
        for path in (root / 'host' / supervisor / 'leases').glob('*/lease.json'):
            identity = json.loads(path.read_bytes())
            result = path.with_name('result.json')
            leases[identity['run_id']] = {'supervisor': supervisor,
                'cleanup_verified': (json.loads(result.read_bytes()).get('cleanup_verified')
                                     if result.exists() else 'unknown')}
    rows = []
    for path in sorted((root / 'runner/runs').glob('*/record.json')):
        record = json.loads(path.read_bytes())
        case = hashes.get(record['input_hash'].removeprefix('sha256:'))
        if case != 'success':
            continue
        row = {key: record.get(key) for key in ('run_id', 'thread_id', 'status',
            'attempt_finished', 'evidence_complete', 'completion_basis', 'error_category',
            'requirements_revision', 'snapshot_ready', 'controller_cleanup')}
        closure = record.get('evidence_closure') or {}
        precheck = record.get('precheck') or {}
        row.update(case=case, turn_count=len(record.get('turns', [])),
                   closure={key: closure.get(key) for key in ('version', 'reason', 'item_count', 'turn_count')},
                   precheck={key: precheck.get(key) for key in ('installed', 'call_count')},
                   lease=leases.get(record['run_id']),
                   github_scope_present=bool(record.get('github_scope')),
                   cleanup_verified=record.get('container_ownership', {}).get('cleanup_verified'))
        answer = json.loads(record['answer'])
        outcome = answer.get('task_outcome')
        row['task_outcome'] = outcome if outcome in ('success', 'failure') else 'unknown'
        checks = []
        commands = []
        for line in (path.parent / 'raw-events.jsonl').read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            if event.get('method') == 'item/tool/call':
                result = precheck_response(record['output_requirements'],
                                          event['params'], record['thread_id'])
                check = json.loads(result['contentItems'][0]['text'])
                checks.append({'contract_status': check['contract_status'],
                               'error_codes': [item['code'] for item in check['errors']]})
            item = event.get('params', {}).get('item', {})
            if event.get('method') == 'item/completed' and item.get('type') == 'commandExecution':
                commands.append({'exit_code': item.get('exitCode'),
                    'missing_remote_helper': "'remote-laomedo' is not a git command" in item.get('aggregatedOutput', '')})
        row['precheck_recomputed_from_bound_calls'] = checks
        row['commands'] = commands
        report = path.parent / 'post-run/experiments/exp139/issue-report.md'
        row['exact_report_bytes'] = report.exists() and sha256(report.read_bytes()).hexdigest() == config['report_sha256']
        graph = json.loads((root / ('amend05-' + case + '.json')).read_bytes())
        row['graph_result'] = graph['graph_result']
        rows.append(row)
    with closing(sqlite3.connect(root / 'host/write-budget.sqlite')) as db:
        attempts = [row[0] for row in db.execute('SELECT operation FROM attempts ORDER BY operation')]
    with closing(sqlite3.connect(root / 'host/mediator/mediator.sqlite')) as db:
        active = db.execute('SELECT COUNT(*) FROM grants WHERE revoked_at IS NULL').fetchone()[0]
    probe = socket.socket()
    try:
        probe.settimeout(1)
        listening = probe.connect_ex(('127.0.0.1', 8779)) == 0
    finally:
        probe.close()
    return {'experiment': 'EXP-139', 'result': 'blocked_no_go',
        'execution_source': activation['source_sha'], 'manifest_sha256': activation['manifest_sha256'],
        'amendments': ['AMENDMENT-05'], 'ledger': ledger,
        'report_sha256': config['report_sha256'], 'write_attempts': attempts,
        'draft_pr': None, 'active_github_grants': active, 'runner_listening': listening,
        'runs': rows, 'historical_observation': 'OBSERVATION.json',
        'preserved_no_turn_startup_run': '7391913c-318f-4317-8c68-fda10b84769d',
        'blockers': ['required_local_run_branch_absent'],
        'unverified': ['live_success_publication', 'published_report_readback'],
        'scope': 'bounded_single_user_local_only'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    result = observe(args.state.resolve())
    target = Path(__file__).with_name('AMEND05-OBSERVATION.json')
    target.write_bytes((json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'ledger': result['ledger'], 'write_attempts': result['write_attempts'],
                      'run_count': len(result['runs']), 'result': result['result']}))

