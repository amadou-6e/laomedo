"""One explicitly approved live cancellation turn; private records and no retries."""
import argparse
import json
import subprocess
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import acceptance as a


def call(path, payload):
    try:
        capability = (a.STATE / 'runs-state/api-token').read_text(encoding='utf-8').strip()
        with urlopen(Request('http://127.0.0.1:8768' + path,
                data=json.dumps(payload).encode(), headers={'Content-Type':'application/json',
                    'Authorization': 'Bearer ' + capability}), timeout=180) as response:
            return json.load(response)
    except HTTPError as error:
        return json.load(error)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approved-model-turn', action='store_true')
    args = parser.parse_args()
    if not args.approved_model_turn:
        parser.error('explicit approval required')
    root = a.STATE / 'runs-state/runs'
    before = set(root.iterdir())
    prior_workers = set(subprocess.check_output(['docker','ps','--format','{{.Names}}'], text=True).splitlines())
    refs = json.loads((a.STATE/'skill-references.json').read_text())['skills']
    result = {}
    def start():
        result.update(call('/v1/runs', {'task': 'Use laomedo_exec exactly once to execute: '
            'test ! -e /draft/agent-marker.txt && sleep 30 && printf LATE > /draft/cancel-late.txt. '
            'Do not invoke any other tool or retry.', 'model':'opencode-go/gpt-6-luna',
            'effort':'default', 'skill_refs':refs}))
    thread = threading.Thread(target=start, daemon=True)
    thread.start()
    deadline = time.monotonic()+100
    owned_workers = []
    run_id = None
    while time.monotonic()<deadline and thread.is_alive():
        folders = set(root.iterdir())-before
        if len(folders)==1:
            run_id=next(iter(folders)).name
        workers=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
        owned_workers=[name for name in workers if name.startswith('laomedo-oc-worker-') and name not in prior_workers]
        if owned_workers and run_id:
            break
        time.sleep(.25)
    if not owned_workers or not run_id:
        raise RuntimeError('agent_command_not_observed; submitted turn remains counted')
    acknowledgement=call('/v1/runs/'+run_id+'/cancel', {})
    thread.join(70)
    remaining=set(subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines())
    workspace=root/run_id/'workspace'
    summary={'run_id':run_id, 'cancel_acknowledged':acknowledgement.get('cancel_acknowledged'),
        'status':result.get('status'), 'request_finished':not thread.is_alive(),
        'owned_workers_absent':not(set(owned_workers)&remaining),
        'late_file_absent':not(workspace/'cancel-late.txt').exists(),
        'fresh_marker_absent':not(workspace/'agent-marker.txt').exists()}
    a._json(a.STATE/'cancel-summary.json',summary)
    print(json.dumps(summary))
    if not all(summary.get(name) for name in ('cancel_acknowledged','request_finished','owned_workers_absent','late_file_absent','fresh_marker_absent')):
        raise RuntimeError('cancellation_acceptance_incomplete')


if __name__=='__main__':
    main()
