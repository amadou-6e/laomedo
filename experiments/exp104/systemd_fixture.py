"""S14 fixture: real systemd/production lease core, synthetic provider only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib import request, error

from laomedo.github_mediation import MediationStore, MediationError
from laomedo.lease_service import LeaseClient, LeaseService, _write_json
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService

STATE = Path('/var/lib/laomedo-s14')
REPOSITORY = 'synthetic/disposable'
SCRIPT = '/opt/experiments/exp104/systemd_fixture.py'


def read(name):
    return json.loads((STATE / name).read_text(encoding='utf-8'))


def wait(check, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError('fixture_wait_expired')


def ctl(*args):
    return subprocess.check_output(['systemctl', *args], text=True, timeout=30).strip()


def unit(name):
    values = ctl('show', name, '--property=MainPID,ControlGroup,KillMode,Restart').splitlines()
    return dict(value.split('=', 1) for value in values)


def membership(pid):
    return Path(f'/proc/{pid}/cgroup').read_text()


def initialize():
    STATE.mkdir(mode=0o700)
    authority = RunGrantAuthority(STATE / 'authority.sqlite')
    for side in ('a', 'b'):
        ref = authority.approve(invocation_id='s14-' + side, repository=REPOSITORY,
                                branch='s14-' + side, reviewed_by='synthetic-controller',
                                operations={'pr_create', 'pr_update'})
        authority.bind_run(ref, 's14-' + side)
    units = {'laomedo-s14-broker.service': 'service',
             'laomedo-s14-a.service': 'runner a', 'laomedo-s14-b.service': 'runner b'}
    for name, command in units.items():
        Path('/etc/systemd/system', name).write_text(
            '[Unit]\nDescription=Disposable S14 fixture\n'
            '[Service]\nType=simple\nEnvironment=PYTHONPATH=/opt\n'
            f'ExecStart=/usr/bin/python3 {SCRIPT} {command}\n'
            'KillMode=control-group\nRestart=no\nTimeoutStopSec=5\n'
            'NoNewPrivileges=yes\n', encoding='utf-8')
    ctl('daemon-reload')
    ctl('start', 'laomedo-s14-broker.service')
    wait(lambda: (STATE / 'mediator.json').exists() and (STATE / 'lease/service.json').exists())
    ctl('start', 'laomedo-s14-a.service', 'laomedo-s14-b.service')
    wait(lambda: (STATE / 'a.json').exists() and (STATE / 'b.json').exists())


def service():
    store = MediationStore(STATE / 'mediator.sqlite')
    authority = RunGrantAuthority(STATE / 'authority.sqlite')
    lease = LeaseService(STATE / 'lease', mediator=store,
                         mediation_authority=authority.authorize_lease,
                         cleanup=lambda *_: (False, 'synthetic_no_stage_container'))
    lock = threading.Lock()

    def transport(repository, operation, payload, **_):
        with lock, (STATE / 'provider.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'repository': repository, 'operation': operation,
                                     'marker': payload['marker'], 'at': time.monotonic()}) + '\n')
        if payload['title'] == 'synthetic-lost-response':
            raise RuntimeError('synthetic_response_lost')
        return {'number': 1 if payload.get('head') == 's14-a' else 2}

    mediator = MediationHTTPService(store, transport)
    _write_json(STATE / 'mediator.json', {'instance': mediator.instance, 'port': mediator.port,
                                        'pid': os.getpid()})
    threading.Thread(target=mediator.serve, daemon=True).start()
    lease.serve()


def runner(side):
    client = LeaseClient(STATE / 'lease', run_id='s14-' + side, name='synthetic-' + side,
                         token='s14-lease-' + side, cancelled=threading.Event(),
                         mediation_request={'invocation_id': 's14-' + side,
                                            'repository': REPOSITORY, 'branch': 's14-' + side})
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(240)'])
    _write_json(STATE / (side + '.json'), {'pid': os.getpid(), 'child': child.pid,
                                        'grant_id': client.grant_id})
    time.sleep(240)


def invoke(side, effect, title, *, create=False):
    bearer = (STATE / 'lease/leases' / ('s14-lease-' + side) / 'grant.secret').read_text()
    info = read('mediator.json')
    payload = {'title': title, 'body': 's14-marker-' + side, 'marker': 's14-marker-' + side,
               'head': 's14-' + side, 'base': 'main'}
    if not create:
        payload.update(number=1 if side == 'a' else 2,
                       expected={'title': 'previous', 'body': 'previous', 'head_sha': 'a' * 40})
    call = request.Request(f"http://127.0.0.1:{info['port']}/v1/mediate", method='POST',
                           data=json.dumps({'repository': REPOSITORY,
                                            'operation': 'pr_create' if create else 'pr_update',
                                            'payload': payload, 'effect_id': effect}).encode(),
                           headers={'Authorization': 'Bearer ' + bearer,
                                    'X-Laomedo-Mediator-Instance': info['instance'],
                                    'Content-Type': 'application/json'})
    try:
        response = request.urlopen(call, timeout=10)
    except error.HTTPError as failure:
        response = failure
    with response:
        return {'http': response.code, 'body': json.loads(response.read(1024 * 1024))}


def count():
    path = STATE / 'provider.jsonl'
    return len(path.read_text().splitlines()) if path.exists() else 0


def capture():
    result = {'stage': 'initialize', 'status': 'incomplete'}
    try:
        initialize()
        result['stage'] = 'unit_membership'
        result['version'] = ctl('--version').splitlines()[0]
        result['pid1'] = Path('/proc/1/comm').read_text().strip()
        result['units'] = {side: unit(name) for side, name in
                           [('service', 'laomedo-s14-broker.service'),
                            ('a', 'laomedo-s14-a.service'), ('b', 'laomedo-s14-b.service')]}
        result['runners'] = {side: read(side + '.json') for side in ('a', 'b')}
        result['membership'] = {side: {key: membership(data[key]) for key in ('pid', 'child')}
                                for side, data in result['runners'].items()}
        result['stage'] = 'positive_and_replay'
        result['a_initial'] = invoke('a', 's14-a-create', 'a', create=True)
        result['b_initial'] = invoke('b', 's14-b-create', 'b', create=True)
        result['initial_count'] = count()
        result['a_replay'] = invoke('a', 's14-a-create', 'a', create=True)
        result['replay_count'] = count()
        result['stage'] = 'kill_a'
        result['kill_start'] = time.monotonic()
        ctl('kill', '--kill-who=all', '--signal=KILL', 'laomedo-s14-a.service')
        result['kill_finished'] = time.monotonic()
        wait(lambda: all(not Path(f'/proc/{pid}').exists()
                          for pid in result['runners']['a'].values() if isinstance(pid, int)), 5)
        result['a_parent_child_gone'] = True
        path = STATE / 'lease/leases/s14-lease-a/revoked.json'
        wait(path.exists, 60)
        result['revoked'] = json.loads(path.read_text())
        result['before_denial_count'] = count()
        result['a_denied'] = invoke('a', 's14-a-after-loss', 'denied')
        result['denied_at'] = time.monotonic()
        result['after_denial_count'] = count()
        result['b_after_denial'] = invoke('b', 's14-b-after-loss', 'b continues')
        result['b_effect_at'] = time.monotonic()
        result['after_b_count'] = count()
        result['surviving_units'] = {'service': unit('laomedo-s14-broker.service'),
                                     'b': unit('laomedo-s14-b.service')}
        result['stage'] = 'unknown_controls'
        result['unknown'] = invoke('b', 's14-unknown', 'synthetic-lost-response')
        result['unknown_count'] = count()
        result['unknown_replay'] = invoke('b', 's14-unknown', 'synthetic-lost-response')
        result['unknown_replay_count'] = count()
        result['conflict'] = invoke('b', 's14-unknown', 'changed-content')
        result['conflict_count'] = count()
        result['stage'] = 'service_restart'
        old = read('mediator.json')
        ctl('restart', 'laomedo-s14-broker.service')
        wait(lambda: read('mediator.json')['instance'] != old['instance'])
        result['restarted_unit'] = unit('laomedo-s14-broker.service')
        result['b_restart_denied'] = invoke('b', 's14-b-after-restart', 'denied')
        result['restart_count'] = count()
        store = MediationStore(STATE / 'mediator.sqlite')
        result['old_lease_renewed'] = store.renew_lease(run_id='s14-b', lease_token='s14-lease-b',
            lease_scope=str(STATE / 'lease'), ttl_seconds=50)
        _, expired = store.issue(run_id='s14-expiry', invocation_id='expiry', repository=REPOSITORY,
                                 operations={'actions_read'}, ttl_seconds=.1,
                                 lease_token='expiry', lease_scope=str(STATE / 'lease'),
                                 service_instance='synthetic-expiry')
        time.sleep(.2)
        result['expired_renewed'] = store.renew_lease(run_id='s14-expiry', lease_token='expiry',
            lease_scope=str(STATE / 'lease'), ttl_seconds=50)
        try:
            store.invoke(token=expired, repository=REPOSITORY,
                operation='actions_read', payload={'resource': 'runs'}, effect_id=None,
                transport=lambda *_: (_ for _ in ()).throw(RuntimeError('unexpected_dispatch')))
            result['expired_invocation'] = {'error': 'unexpected_success'}
        except MediationError as failure:
            result['expired_invocation'] = {'error': failure.code}
        result['stage'] = 'complete'
        result['status'] = 'captured'
    except Exception as failure:
        result['error_class'] = type(failure).__name__
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    {'service': service, 'runner': lambda: runner(sys.argv[2]), 'capture': capture}[sys.argv[1]]()
