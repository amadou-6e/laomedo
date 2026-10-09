"""Frozen one-shot real host-deadline/cancel cases; private outputs only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from experiments.exp117.support import (
    ROOT, PILOT, LEDGER, CAP, _hash, _private_empty, _port, _events,
    _owned_container_absent, _cleanup_runner_runs, _audit_requests,
)
from laomedo.local_runner import LocalRunner, serve
from laomedo.skill_store import SkillStore
from laomedo.workflow_run_store import WorkflowRunStore
from laomedo.handoff_http import RunnerAdapter
from laomedo.handoffs import HandoffError
from laomedo.runner_trace_bridge import RunnerTraceBridge


def reserve_entry(state, case, *, entry=None, result=None):
    lock = LEDGER.with_suffix('.lock')
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        ledger = json.loads(LEDGER.read_text(encoding='utf-8-sig'))
        if ledger.get('cap') != CAP:
            raise RuntimeError('ledger_cap_mismatch')
        if entry is None:
            expected = {'before': 10, 'during': 11}[case]
            if len(ledger['attempts']) != expected or expected >= CAP or any(
                    row.get('case_kind') == 'exp66-' + case for row in ledger['attempts']):
                raise RuntimeError('case_repeated_or_out_of_order')
            entry = uuid4().hex
            ledger['attempts'].append({'id': entry, 'case_kind': 'exp66-' + case,
                'state_dir': str(state), 'submitted_at': time.time(),
                'result': 'submitted_unknown'})
        else:
            rows = [r for r in ledger['attempts'] if r['id'] == entry]
            if len(rows) != 1:
                raise RuntimeError('ledger_entry_missing')
            rows[0].update(result=result, finished_at=time.time())
        pending = LEDGER.with_suffix('.pending')
        pending.write_text(json.dumps(ledger, indent=2))
        os.replace(pending, LEDGER)
        return entry, len(ledger['attempts'])
    finally:
        lock.unlink(missing_ok=True)


def reopen(path, run_id):
    """Fresh process opens only the durable store; cannot dispatch anything."""
    code = ('import json,sys;from laomedo.workflow_run_store import WorkflowRunStore;'
            'print(json.dumps(WorkflowRunStore(sys.argv[1]).trace_snapshot(sys.argv[2])))')
    return json.loads(subprocess.check_output(
        [sys.executable, '-c', code, str(path), run_id], cwd=ROOT, text=True, timeout=20))


def long_started(events):
    return any(e.get('method') == 'item/started' and
               (e.get('params', {}).get('item') or {}).get('type') == 'commandExecution' and
               'sleep 30' in str((e.get('params', {}).get('item') or {}).get('command'))
               for e in events)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--case', choices=['before', 'during'], required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight-only', action='store_true')
    modes.add_argument('--allow-one-model-turn', action='store_true')
    args = parser.parse_args()
    if args.allow_one_model_turn and subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True).strip():
        parser.error('reviewed_source_must_be_committed_and_clean')
    state = _private_empty(args.state)
    skill = SkillStore(state/'skills').import_skill('laomedo-pilot', PILOT/'skill')
    runner = LocalRunner(state/'runner', state/'skills', PILOT/'source', max_model_turns=1)
    preflight = runner.preflight()
    if preflight.get('status') != 'ready' or not any(m.get('id') == 'gpt-6-luna' and
            'low' in m.get('efforts', []) for m in preflight.get('models', [])):
        raise RuntimeError('native_preflight_failed')
    if args.preflight_only:
        print(json.dumps({'case': args.case, 'runner_ready': True, 'model_turns': 0}))
        return
    server = serve(runner, port=_port())
    routes = state/'routes.jsonl'
    _audit_requests(server, routes)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    adapter = RunnerAdapter({'codex': f'http://127.0.0.1:{port}'},
        {'codex': state/'runner/api-token'})
    store = WorkflowRunStore(state/'join.sqlite3')
    bridge = RunnerTraceBridge(store, adapter)
    flow = json.loads((ROOT/'examples/native-codex-node/flow.json').read_text())
    codes = {n['id']: n['data']['node']['template']['code']['value']
             for n in flow['data']['nodes']}
    run = store.reserve(graph=flow['data'], component_code=codes,
        resolved_config={'case': args.case, 'host_wait_seconds': 5},
        trigger={'type': 'direct', 'experiment': 'EXP-66-native'})
    host_id = run['run_id']
    task_path = ROOT/f'experiments/exp66/TASK-{args.case}.txt'
    handoff = {'operation': 'fresh', 'execution_id': str(uuid4()), 'step': 0,
        'target': {'provider': 'codex', 'model': 'gpt-6-luna', 'effort': 'low'},
        'task': task_path.read_text(), 'source': None, 'workspace_policy': 'independent',
        'artifacts': [], 'skill_refs': [{k: skill[k] for k in
                                      ('skill_id', 'revision_id', 'tree_hash')}]}
    pins = {'implementation': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'protocol_sha256': _hash(ROOT/'experiments/exp66/NATIVE-PROTOCOL.md'),
        'task_sha256': _hash(task_path), 'image_id': preflight['image_id'],
        'model': 'gpt-6-luna', 'effort': 'low', 'host_wait_seconds': 5,
        'native_effect_delay_seconds': 30, 'effect_observation_seconds': 31,
        'clock_resolution': time.get_clock_info('monotonic').resolution,
        'cross_machine_timing_used': False}
    (state/'pins.json').write_text(json.dumps(pins,indent=2))
    entry = None
    native_id = None
    category = 'not_submitted'
    teardown = {}
    try:
        entry, used = reserve_entry(state, args.case)
        category = 'submitted_unknown'
        start = time.monotonic()
        start_wall = datetime.now(timezone.utc).isoformat()
        try:
            bridge.dispatch(host_id, 'LaomedoCodexAgent-native', handoff,
                deadline=start+5, cancelled=threading.Event())
            raise RuntimeError('native_completed_before_host_deadline')
        except HandoffError as exc:
            if str(exc) != 'runner_result_pending':
                raise RuntimeError('unexpected_dispatch_outcome') from exc
        timed = time.monotonic()
        before = store.trace_snapshot(host_id)
        inv = before['invocation']['invocation_id']
        native_id = before['invocation']['runner_run_id']
        if not native_id or before['run_status'] != 'incomplete' or before['evidence_complete']:
            raise RuntimeError('missing_durable_timeout_binding')
        (state/'trace-at-timeout.json').write_text(json.dumps(before,indent=2))
        raw = state/'runner/runs'/native_id/'raw-events.jsonl'
        effect = state/'runner/runs'/native_id/'workspace/native-effect.txt'
        deadline = time.monotonic()+60
        seen = None
        while time.monotonic()<deadline:
            events = _events(raw)
            native = runner.status(native_id)
            if native['status'] not in {'prepared','running'}:
                raise RuntimeError('native_terminal_before_cancel_boundary')
            if long_started(events) and (args.case == 'before' or
                    effect.exists() and effect.read_bytes() == b'FIRST\n'):
                seen = time.monotonic()
                break
            time.sleep(.05)
        if seen is None:
            raise RuntimeError('cancel_boundary_not_observed')
        observed_effect = None
        if args.case == 'before':
            if effect.exists():
                raise RuntimeError('effect_preceded_before_case_cancel')
        else:
            observed_effect = hashlib.sha256(effect.read_bytes()).hexdigest()
            store.record_effect(host_id,inv,source='exp66-host-file-observation',
                source_ref='sha256:'+observed_effect,
                source_time=datetime.now(timezone.utc).isoformat())
        cancel_at = time.monotonic()
        bridge.cancel(host_id,inv,handoff['execution_id'])
        deadline = time.monotonic()+45
        terminal = None
        while time.monotonic()<deadline:
            terminal = bridge.observe_terminal(host_id,inv)
            if terminal.get('status') not in {'prepared','running'} and (
                    terminal.get('status') != 'cancelled' or terminal.get('cancel_confirmed') is True):
                break
            time.sleep(.1)
        time.sleep(max(0,seen+31-time.monotonic()))
        final = runner.status(native_id)
        events = _events(raw)
        native_statuses = [e.get('params',{}).get('turn',{}).get('status')
                           for e in events if e.get('method') == 'turn/completed']
        file_ok = not effect.exists() if args.case == 'before' else effect.read_bytes() == b'FIRST\n'
        after = reopen(state/'join.sqlite3',host_id)
        unchanged = all(before[k] == after[k] for k in ('run_id','trace_id','dispatch_attempts')) and all(
            before['invocation'][k] == after['invocation'][k] for k in
            ('invocation_id','runner_run_id','runner_raw_event_ref','runner_request_hash'))
        receipts = [r['kind'] for r in after['receipts']]
        native_receipts = [r['payload'] for r in after['receipts'] if r['kind']=='runner_terminal']
        starts = sum(r.get('kind')=='start' for r in _events(routes))
        cancels = sum(r.get('kind')=='cancel' for r in _events(routes))
        passed = (unchanged and timed>=start+5 and seen>timed and cancel_at>=seen and
            final['status']=='cancelled' and final.get('cancel_confirmed') is True and
            'interrupted' in native_statuses and _owned_container_absent(final) and file_ok and
            after['run_status']=='incomplete' and after['invocation']['error_class']=='timeout' and
            after['invocation']['effect_state']==('unknown' if args.case=='before' else 'observed') and
            after['stream_state']=='partial' and not after['evidence_complete'] and
            'runner_result_pending' in receipts and
            sum(r.get('cancel_confirmed') is True for r in native_receipts)==1 and
            all(r['native_status']=='cancelled' and r['workflow_outcome_preserved'] is True
                for r in native_receipts) and starts==1 and cancels==1)
        category = f'native_{args.case}_effect_passed' if passed else 'native_timeout_inconclusive'
        summary={'category':category,'case':args.case,'shared_turn_count':used,
            'timeout_layer':'host_adapter_wait','langflow_server_408_retested':False,
            'host_start_utc':start_wall,'timeout_elapsed_seconds':timed-start,
            'command_boundary_after_timeout_seconds':seen-timed,'cancel_elapsed_seconds':cancel_at-start,
            'run_status':after['run_status'],'native_status':final['status'],
            'cancel_confirmed':final.get('cancel_confirmed'), 'native_completion_statuses':native_statuses,
            'container_absent':_owned_container_absent(final),'effect_file_matches_expected':file_ok,
            'effect_state':after['invocation']['effect_state'],'effect_sha256':observed_effect,
            'same_identity_after_reopen':unchanged,'evidence_complete':after['evidence_complete'],
            'stream_state':after['stream_state'],'receipt_kinds':receipts,'raw_event_count':len(events),
            'raw_event_sha256':_hash(raw),'dispatches':starts,'cancels':cancels}
        (state/'sanitized.json').write_text(json.dumps(summary,indent=2))
        (state/'trace-after-reopen.json').write_text(json.dumps(after,indent=2))
        print(json.dumps(summary))
    finally:
        if entry:
            reserve_entry(state,args.case,entry=entry,result=category)
        try:
            teardown['runs']=_cleanup_runner_runs(runner,state/'runner/runs',native_id)
            teardown['exact_cleanup_verified']=all(r['exact_cleanup_verified'] for r in teardown['runs'])
        except Exception as exc:
            teardown['cleanup_error_class']=type(exc).__name__
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        teardown['runner_server_stopped']=not thread.is_alive()
        (state/'teardown.json').write_text(json.dumps(teardown,indent=2))

if __name__ == '__main__':
    main()
