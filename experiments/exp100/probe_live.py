"""Prospectively frozen S12; never invoked by tests; one explicit live attempt."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.agent_cli import prepare_commands
from laomedo.container_lease import cleanup_exact, inspect_exact, LABEL_RUN, LABEL_TOKEN
from laomedo.github_mediation import MediationStore, _request_hash
from laomedo.github_rest_transport import GitHubRestTransport, ISSUE_GRAPHQL_QUERY, _NoRedirect
from laomedo.host_token_connection import HostTokenConnection
from laomedo.local_runner import GIT_IMAGE_ID
from laomedo.mediation_service import MediationHTTPService

IDENTITY = 'exp100-live-s12-20261010-a'
DISPOSABLE = 'ga84jog/laomedo-exp104-disposable-20261007'
PUBLIC = 'amadou-6e/laomedo'
SPEC = '04fade6d88cc4c6d5c494c7e566c5cacbad93b09'
JOB, ACTION_RUN = 114224703478, 38056050461
ISSUE = {'title': 'Laomedo EXP-100 S12 reviewed integration test',
         'body': IDENTITY + '-reviewed-issue\nDisposable one-shot mediated issue-create acceptance test. No automatic retry.',
         'marker': IDENTITY + '-reviewed-issue', 'reviewed_proposal_id': IDENTITY + '-proposal'}
REQUIRED = {'pr_list', 'issue_list_preflight', 'graphql_preflight', 'rest_get',
            'actions_runs', 'actions_job', 'unsupported', 'credential_export',
            'wrong_repository', 'altered_issue', 'issue_create', 'issue_view',
            'issue_list_positive', 'graphql_positive', 'confirmed_replay', 'revoked'}


def write_json(path, value):
    with path.open('w', encoding='utf8', newline='\n') as file:
        json.dump(value, file, indent=2, sort_keys=True); file.write('\n')
        file.flush(); os.fsync(file.fileno())


class BoundedOpener:
    """Independent provider boundary: save attempted dispatch before network."""
    def __init__(self, journal, *, base=None):
        self.base = base or request.build_opener(_NoRedirect)
        self.journal = journal
        self.rows = []
        self.lock = threading.Lock()

    def open(self, call, timeout):
        url, method = parse.urlsplit(call.full_url), call.get_method()
        if (url.scheme != 'https' or url.netloc != 'api.github.com' or
                url.query or url.fragment):
            raise ValueError('provider_target_denied')
        body = json.loads(call.data) if call.data else None
        write = method == 'POST' and url.path == '/repos/' + DISPOSABLE + '/issues'
        if write:
            if body != {key: ISSUE[key] for key in ('title', 'body')}:
                raise ValueError('provider_issue_bytes_denied')
        elif method == 'POST':
            if url.path != '/graphql' or body != {'query': ISSUE_GRAPHQL_QUERY,
                    'variables': dict(zip(('owner', 'name'), DISPOSABLE.split('/')))}:
                raise ValueError('provider_post_denied')
        elif method != 'GET' or not (url.path.startswith('/repos/' + DISPOSABLE + '/') or
                url.path in {'/repos/' + PUBLIC + '/actions/runs',
                             '/repos/' + PUBLIC + '/actions/jobs/' + str(JOB)}):
            raise ValueError('provider_read_denied')
        with self.lock:
            if (write and any(row['write'] for row in self.rows)) or (
                    not write and sum(not row['write'] for row in self.rows) >= 80):
                raise ValueError('provider_budget_exhausted')
            row = {'method': method, 'path': url.path, 'write': write,
                   'attempt': len(self.rows) + 1, 'state': 'sending'}
            self.rows.append(row)
            # Persist before attempting a POST, even if no response ever arrives.
            write_json(self.journal, self.rows)
        try:
            response = self.base.open(call, timeout=min(timeout, 15))
            row.update(state='response', status=response.status)
            return response
        except Exception as failure:
            row.update(state='error', status=getattr(failure, 'code', None))
            raise
        finally:
            with self.lock: write_json(self.journal, self.rows)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode()).hexdigest()


def check(observed):
    rows = observed['cases']
    if len(rows) != len(REQUIRED) or {row['case'] for row in rows} != REQUIRED:
        raise ValueError('missing_or_duplicate_case')
    for row in rows:
        if row.get('passed') is not True: raise ValueError('case_failed')
        if row['case'] not in {'unsupported', 'credential_export', 'wrong_repository',
                               'altered_issue', 'revoked', 'confirmed_replay'} and (
                row.get('exit') != 0 or row['calls'] < 1 or
                not re.fullmatch(r'[0-9a-f]{64}', row.get('output_hash', ''))):
            raise ValueError('positive_not_observed')
    refusals = {'unsupported': (2, 'unsupported_command'),
                'credential_export': (2, 'unsupported_command'),
                'wrong_repository': (2, 'repository_mismatch'),
                'altered_issue': (3, 'mediator_denied:issue_review_denied'),
                'revoked': (3, 'mediator_denied:grant_unavailable')}
    for name, expected in refusals.items():
        row = next(row for row in rows if row['case'] == name)
        if (row.get('exit'), row.get('reason')) != expected or row['calls'] != 0:
            raise ValueError('false_refusal')
    writes = [row for row in observed['provider_calls'] if row['write']]
    if len(writes) != 1 or writes[0]['path'] != '/repos/' + DISPOSABLE + '/issues':
        raise ValueError('write_count_invalid')
    effect = observed['effect']
    if (effect['state'] != 'confirmed' or effect['operation'] != 'issue_create' or
            effect['run_id'] != IDENTITY + '-disposable' or
            effect['grant_id'] != observed['grants']['disposable'] or
            effect['request_hash'] != _request_hash(DISPOSABLE, 'issue_create', ISSUE)):
        raise ValueError('effect_attribution_invalid')
    if observed['issue']['title'] != ISSUE['title'] or observed['issue']['body'] != ISSUE['body']:
        raise ValueError('issue_bytes_invalid')
    replay = next(row for row in rows if row['case'] == 'confirmed_replay')
    if replay['calls'] != 0 or replay['number'] != observed['issue']['number']:
        raise ValueError('replay_invalid')
    if not observed['cleanup']['verified'] or observed['cleanup']['elapsed'] > 30:
        raise ValueError('cleanup_unverified')
    if observed['model_turns'] != 0: raise ValueError('unexpected_model_use')
    job = observed['job']
    if job['id'] != JOB or job['run_id'] != ACTION_RUN or job['status'] != 'completed':
        raise ValueError('job_evidence_invalid')


def run(token_file, source_sha, review_file):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    manifest_path = Path(__file__).with_name('LIVE-MANIFEST.json')
    manifest_hash = sha256(manifest_path.read_bytes()).hexdigest()
    manifest = json.loads(manifest_path.read_bytes())
    if git('rev-parse', 'HEAD') != source_sha or git('status', '--porcelain'):
        raise ValueError('source_not_exact_clean')
    if json.loads(review_file.read_bytes()) != {'identity': IDENTITY, 'source_sha': source_sha,
            'manifest_sha256': manifest_hash, 'verdict': 'approve'}:
        raise ValueError('exact_prerun_review_required')
    if (manifest['identity'], manifest['spec_sha'], manifest['image']) != (IDENTITY, SPEC, GIT_IMAGE_ID):
        raise ValueError('manifest_invalid')
    for path, expected in manifest['source_hashes'].items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError('frozen_source_changed')
    private = Path(tempfile.gettempdir()) / 'laomedo-live-command-campaign' / IDENTITY
    private.mkdir(parents=True, exist_ok=True)
    with (private / 'consumed.claim').open('x') as file: file.write(IDENTITY)
    root = Path(tempfile.mkdtemp(prefix=IDENTITY + '-'))
    observation_path = private / 'observation.json'
    observed = {'identity': IDENTITY, 'source_sha': source_sha, 'spec_sha': SPEC,
                'manifest_sha256': manifest_hash, 'image': GIT_IMAGE_ID,
                'result': 'incomplete', 'cases': [], 'model_turns': 0}
    opener = BoundedOpener(private / 'provider-attempts.json')
    store, owners, services, grants, capabilities = None, {}, [], {}, {}
    stopped = threading.Event(); renewal = None
    deadline = time.monotonic() + 600
    def command(args, stdin=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise ValueError('overall_deadline')
        result = subprocess.run(args, input=stdin, capture_output=True, timeout=min(30, remaining))
        try: value = json.loads(result.stdout)
        except (ValueError, UnicodeError): value = None
        codes = [line for line in result.stderr.decode(errors='replace').splitlines()
                 if re.fullmatch(r'(?:mediator_denied:)?[a-z][a-z0-9_]{1,127}', line)]
        return result.returncode, value, codes[0] if codes else 'unclassified'
    try:
        connections = {side: HostTokenConnection(connection_id=IDENTITY + '-' + side,
            generation=1, repository=repo, token_file=token_file, key='GH_LAOMEDO',
            forbidden_mount=root) for side, repo in (('disposable', DISPOSABLE), ('public', PUBLIC))}
        def current(cid, generation, repo):
            return any(connection.current(cid, generation, repo) for connection in connections.values())
        store = MediationStore(root / 'effects.sqlite', connection_is_current=current)
        transports = {side: GitHubRestTransport(connection.repository, connection.token, opener=opener)
                      for side, connection in connections.items()}
        wrappers = prepare_commands(root, DISPOSABLE, 'unused')
        for side, connection in connections.items():
            run_id = IDENTITY + '-' + side
            operations = ({'pr_list', 'issue_list', 'issue_create', 'api_rest_read'}
                          if side == 'disposable' else {'actions_read', 'api_rest_read'})
            grant, capability = store.issue(run_id=run_id, invocation_id=run_id + '-invocation',
                repository=connection.repository, operations=operations, ttl_seconds=60,
                connection_id=connection.connection_id, connection_generation=1,
                approval_identity=IDENTITY + '-owner-approval',
                reviewed_issue_requests={ISSUE['reviewed_proposal_id']: ISSUE} if side == 'disposable' else {})
            grants[side], capabilities[side] = grant, capability
            service = MediationHTTPService(store, transports[side]); services.append(service)
            threading.Thread(target=service.serve, daemon=True).start()
            capfile = root / ('capability-' + side); capfile.write_text(capability, encoding='ascii')
            name, label = 'laomedo-live-' + secrets.token_hex(8), secrets.token_hex(16)
            owners[side] = {'name': name, 'run_id': run_id, 'token': label}
            argv = ['docker', 'run', '-d', '--pull=never', '--name', name,
                '--label', LABEL_RUN + '=' + run_id, '--label', LABEL_TOKEN + '=' + label,
                '--network=bridge', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--user=10001:10001', '--pids-limit=64', '--memory=512m',
                '--tmpfs=/tmp:rw,noexec,nosuid,size=64m']
            environment = {'PATH': '/run/laomedo/bin:/usr/local/bin:/usr/bin:/bin',
                'HOME': '/tmp', 'LAOMEDO_REPOSITORY': connection.repository,
                'LAOMEDO_MEDIATOR_URL': 'http://host.docker.internal:' + str(service.port) + '/v1/mediate',
                'LAOMEDO_MEDIATOR_INSTANCE': service.instance,
                'LAOMEDO_CAPABILITY_FILE': '/run/laomedo/capability'}
            for key, value in environment.items(): argv += ['--env', key + '=' + value]
            for src, dst in ((capfile, '/run/laomedo/capability'), (wrappers, '/run/laomedo/bin'),
                (ROOT / 'laomedo/agent_gh_adapter.mjs', '/run/laomedo/gh.mjs'),
                (ROOT / 'laomedo/agent_mediation_client.mjs', '/run/laomedo/mediate.mjs')):
                argv += ['--mount', 'type=bind,source=' + str(src) + ',target=' + dst + ',readonly']
            if command(argv + [GIT_IMAGE_ID, 'sleep', '600'])[0] != 0:
                raise ValueError('launch_failed_no_retry')
        observed['grants'] = grants
        def renew():
            while not stopped.wait(5):
                for side, owner in owners.items():
                    if inspect_exact(**owner)[0] != 'owned' or not store.renew_grant(grants[side], 60):
                        stopped.set(); return
        renewal = threading.Thread(target=renew, daemon=True); renewal.start()
        def m(name, args, side='disposable', stdin=None, effect=None, expected=None):
            if stopped.is_set(): raise ValueError('ownership_or_lease_lost')
            before = len(opener.rows)
            argv = ['docker', 'exec', '-i']
            if effect:
                argv += ['--env=LAOMEDO_EFFECT_ID=' + effect,
                    '--env=LAOMEDO_RECONCILIATION_MARKER=' + ISSUE['marker'],
                    '--env=LAOMEDO_REVIEWED_PROPOSAL_ID=' + ISSUE['reviewed_proposal_id']]
            code, value, reason = command(argv + [owners[side]['name'], 'gh', *args], stdin)
            row = {'case': name, 'exit': code, 'reason': reason,
                   'calls': len(opener.rows) - before, 'passed': code == 0 if expected is None
                   else (code, reason) == expected and len(opener.rows) == before}
            if value is not None: row['output_hash'] = digest(value)
            observed['cases'].append(row); write_json(observation_path, observed)
            if row['passed'] is not True: raise ValueError('command_failed_' + name)
            return value
        def baseline(side, operation, payload):
            connection = connections[side]
            return transports[side](connection.repository, operation, payload,
                connection_id=connection.connection_id, connection_generation=1)
        def match(value, expected):
            if value != expected: raise ValueError('baseline_mismatch')
        match(m('pr_list', ['pr', 'list']), baseline('disposable', 'pr_list', {}))
        match(m('issue_list_preflight', ['issue', 'list']), baseline('disposable', 'issue_list', {}))
        graphql = json.dumps({'query': ISSUE_GRAPHQL_QUERY,
                             'variables': dict(zip(('owner', 'name'), DISPOSABLE.split('/')))}).encode()
        def query(name):
            value = m(name, ['api', 'graphql', '--method', 'POST', '--input', '-'], stdin=graphql)
            match(value['data']['repository']['issues']['nodes'],
                  baseline('disposable', 'issue_list', {'format': 'fixed_graphql'})['items'])
            return value['data']['repository']['issues']['nodes']
        query('graphql_preflight')
        path = '/repos/' + DISPOSABLE + '/branches/main'
        match(m('rest_get', ['api', path]), baseline('disposable', 'api_rest_read', {'path': path}))
        runs = m('actions_runs', ['run', 'list'], 'public')
        # Job state/ID are stable; run-list timestamps can change between reads.
        baseline_runs = baseline('public', 'actions_read', {'resource': 'runs'})
        if not any(row['id'] == ACTION_RUN for row in runs['workflow_runs']) or not any(
                row['id'] == ACTION_RUN for row in baseline_runs['workflow_runs']):
            raise ValueError('fixed_action_run_missing')
        job = m('actions_job', ['api', '/repos/' + PUBLIC + '/actions/jobs/' + str(JOB)], 'public')
        expected_job = baseline('public', 'actions_read', {'job_id': JOB})
        fields = ('id', 'run_id', 'status', 'conclusion')
        match({key: job[key] for key in fields}, {key: expected_job[key] for key in fields})
        if job['id'] != JOB or job['run_id'] != ACTION_RUN or job['status'] != 'completed':
            raise ValueError('job_fixture_mismatch')
        observed['job'] = {key: job[key] for key in fields}
        m('unsupported', ['extension', 'list'], expected=(2, 'unsupported_command'))
        m('credential_export', ['auth', 'token'], expected=(2, 'unsupported_command'))
        m('wrong_repository', ['issue', 'list', '--repo', PUBLIC], expected=(2, 'repository_mismatch'))
        m('altered_issue', ['issue', 'create', '--title', 'Altered title', '--body', ISSUE['body']],
          effect='altered', expected=(3, 'mediator_denied:issue_review_denied'))
        created = m('issue_create', ['issue', 'create', '--title', ISSUE['title'], '--body', ISSUE['body']], effect='reviewed-issue')
        if type(created.get('number')) is not int or created.get('title') != ISSUE['title'] or created.get('body') != ISSUE['body']:
            raise ValueError('issue_response_mismatch_unknown_no_retry')
        number = created['number']; observed['issue'] = {key: created[key] for key in ('number', 'title', 'body')}
        time.sleep(5)  # Prospective Amendment 01; never another POST.
        view = m('issue_view', ['issue', 'view', str(number)])
        direct = baseline('disposable', 'api_rest_read', {'path': '/repos/' + DISPOSABLE + '/issues/' + str(number)})
        match({key: view[key] for key in ('number', 'title', 'body')}, observed['issue'])
        match({key: direct[key] for key in ('number', 'title', 'body')}, observed['issue'])
        listing = m('issue_list_positive', ['issue', 'list'])['items']
        if any('pull_request' in item for item in listing) or not any(
                {key: item[key] for key in ('number', 'title', 'body')} == observed['issue'] for item in listing):
            raise ValueError('issue_list_positive_missing')
        if observed['issue'] not in query('graphql_positive'):
            raise ValueError('graphql_positive_missing')
        before = len(opener.rows)
        replay = store.invoke(token=capabilities['disposable'], repository=DISPOSABLE,
            operation='issue_create', payload=ISSUE, effect_id='reviewed-issue', transport=transports['disposable'])
        observed['cases'].append({'case': 'confirmed_replay', 'passed': replay.get('state') == 'confirmed',
                                  'number': replay['result']['number'], 'calls': len(opener.rows) - before})
        with closing(sqlite3.connect(store.path)) as db:
            db.row_factory = sqlite3.Row
            observed['effect'] = dict(db.execute('SELECT run_id,grant_id,operation,state,request_hash '
                'FROM effects WHERE run_id=? AND effect_id=?',
                (IDENTITY + '-disposable', 'reviewed-issue')).fetchone())
        observed['inventory'] = {}
        for side, owner in owners.items():
            result = subprocess.run(['docker', 'inspect', owner['name']], capture_output=True, timeout=15)
            if result.returncode: raise ValueError('inventory_unavailable')
            entry = json.loads(result.stdout)[0]
            keys = sorted(item.split('=', 1)[0] for item in entry['Config']['Env'])
            mounts = sorted(item['Destination'] for item in entry['Mounts'])
            if any(key.upper().startswith(('GH_', 'GITHUB_', 'GCM_')) or key.upper() in {'GH', 'GH_LAOMEDO'} for key in keys):
                raise ValueError('credential_variable_found')
            if mounts != ['/run/laomedo/bin', '/run/laomedo/capability', '/run/laomedo/gh.mjs', '/run/laomedo/mediate.mjs']:
                raise ValueError('unexpected_mount')
            observed['inventory'][side] = {'environment_keys': keys, 'mount_destinations': mounts}
        stopped.set(); renewal.join(timeout=10)
        store.revoke_run(IDENTITY + '-disposable')
        # Renewal is stopped intentionally; the revoked invocation must still run.
        stopped.clear()
        m('revoked', ['issue', 'list'], expected=(3, 'mediator_denied:grant_unavailable'))
    except Exception as failure:
        code = str(failure)
        observed['error'] = code if re.fullmatch(r'[a-z][a-z0-9_]{1,127}', code) else type(failure).__name__
    finally:
        stopped.set()
        if renewal: renewal.join(timeout=10)
        start = time.monotonic(); verified = True; cleaned = {}
        if store:
            for side in grants:
                try:
                    store.revoke_run(IDENTITY + '-' + side)
                    with closing(sqlite3.connect(store.path)) as db:
                        row = db.execute('SELECT revoked FROM grants WHERE grant_id=?', (grants[side],)).fetchone()
                        verified = verified and row is not None and row[0] == 1
                except Exception: verified = False
        for side, owner in owners.items():
            try: ok, detail = cleanup_exact(**owner)
            except Exception: ok, detail = False, 'cleanup_error'
            cleaned[side] = {'verified': ok, 'detail': detail}; verified &= ok
        for service in services:
            try: service.close()
            except Exception: verified = False
        observed['cleanup'] = {'verified': bool(verified and len(owners) == 2 and len(grants) == 2),
                               'containers': cleaned, 'elapsed': time.monotonic() - start}
        observed['provider_calls'] = opener.rows
        try:
            check(observed)
            if 'error' not in observed: observed['result'] = 'passed'
        except Exception as failure:
            observed.setdefault('error', str(failure) if re.fullmatch(r'[a-z][a-z0-9_]{1,127}', str(failure)) else type(failure).__name__)
        write_json(observation_path, observed)
    return observed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--review-record', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.token_file.resolve(), args.source_sha, args.review_record)
    print(json.dumps({'identity': IDENTITY, 'result': result['result'], 'error': result.get('error')}))
    raise SystemExit(0 if result['result'] == 'passed' else 1)
