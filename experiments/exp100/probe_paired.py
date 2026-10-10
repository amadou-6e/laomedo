"""S11 one-shot direct/mediated synthetic comparison. Never consumes a real token."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import re
import shlex
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.exp100.paired_cases import IDENTITY, MARKER, PROPOSAL, REVIEWED_ISSUE, GRAPHQL_INPUT, check
from experiments.exp100.paired_provider import Provider, REPOSITORY, TOKEN
from experiments.exp104.probe_active_delivery import git, stage_cleanup
from laomedo.agent_cli import configure_remote, prepare_commands
from laomedo.bundle_verifier import BundleVerifier
from laomedo.container_lease import cleanup_exact, inspect_exact, LABEL_RUN, LABEL_TOKEN
from laomedo.github_git_transport import GitHubGitTransport, GitHubMediatedTransport, _base_git_environment
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.github_mediation import MediationStore
from laomedo.local_runner import GIT_IMAGE_ID
from laomedo.mediation_service import MediationHTTPService
from laomedo.verified_git_stage import make_grant_stage_resolver, make_grant_bundle_freezer, classify_verified_workflow

SPEC = '193fdfb2c31e71745943039c05e14d5d72e8309e'


def install_direct_journal(remote, journal):
    hook = remote / 'hooks/post-receive'
    hook.write_text('#!/bin/sh\ncat >> ' + shlex.quote(journal.as_posix()) + '\n',
                    encoding='utf8', newline='\n')
    hook.chmod(0o755)


def received_updates(journal):
    return [line.split() for line in journal.read_text().splitlines()] if journal.exists() else []


def isolated_environment(folder):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('GH_', 'GITHUB_', 'GIT_', 'GCM_', 'LAOMEDO_'))
           and key.upper() not in {'GH', 'GH_LAOMEDO'}}
    env.update({'GH_CONFIG_DIR': str(folder), 'GH_ENTERPRISE_TOKEN': TOKEN,
        'GH_NO_UPDATE_NOTIFIER': '1', 'GH_NO_EXTENSION_UPDATE_NOTIFIER': '1',
        'GH_PROMPT_DISABLED': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0',
        'HOME': str(folder), 'USERPROFILE': str(folder), 'XDG_CONFIG_HOME': str(folder)})
    return env


def run(private, source_sha, review_record):
    expected_private = Path(tempfile.gettempdir()) / 'laomedo-paired-campaign' / IDENTITY
    if private.resolve() != expected_private.resolve():
        raise ValueError('fixed_identity_claim_directory_required')
    if os.name != 'nt' or git(ROOT, 'rev-parse', 'HEAD') != source_sha or \
            git(ROOT, 'status', '--porcelain'):
        raise ValueError('source_or_platform_invalid')
    review = json.loads(review_record.read_bytes())
    manifest = json.loads(Path(__file__).with_name('PAIRED-MANIFEST.json').read_bytes())
    manifest_hash = sha256(Path(__file__).with_name('PAIRED-MANIFEST.json').read_bytes()).hexdigest()
    if review != {'identity': IDENTITY, 'source_sha': source_sha,
                  'manifest_sha256': manifest_hash, 'verdict': 'approve'}:
        raise ValueError('exact_prerun_review_required')
    if manifest['identity'] != IDENTITY or manifest['spec_sha'] != SPEC or \
            manifest['image'] != GIT_IMAGE_ID:
        raise ValueError('manifest_invalid')
    for path, expected in manifest['source_hashes'].items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError('frozen_source_changed')
    private.mkdir(parents=True, exist_ok=True)
    with (private / (IDENTITY + '.claim')).open('x') as file: file.write(IDENTITY)
    root = Path(tempfile.mkdtemp(prefix=IDENTITY + '-'))
    observation = {'identity': IDENTITY, 'source_sha': source_sha, 'spec_sha': SPEC,
        'manifest_sha256': manifest_hash, 'image': GIT_IMAGE_ID, 'cases': [],
        'result': 'incomplete', 'model_turns': 0, 'real_provider_calls': 0}
    deadline = time.monotonic() + 600
    containers, verifiers, servers, grants = {}, [], [], {}
    stopped = threading.Event()
    stage = root / 'private'
    mediated = direct = None
    store = None
    git_calls = []
    def command(args, *, cwd=None, env=None, stdin=None):
        if time.monotonic() >= deadline: raise TimeoutError('overall_deadline_no_retry')
        result = subprocess.run(args, cwd=cwd, env=env, input=stdin, capture_output=True,
                                timeout=min(30, deadline - time.monotonic()))
        try: value = json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError): value = result.stdout.decode(errors='replace').strip()
        safe_codes = [line for line in result.stderr.decode(errors='replace').splitlines()
                      if re.fullmatch(r'(?:mediator_denied:)?[a-z][a-z0-9_]{1,127}', line)]
        return {'exit': result.returncode, 'value': value, 'reason': safe_codes[0] if safe_codes else 'unclassified',
                'stderr_category': 'empty' if not result.stderr else 'nonempty'}
    try:
        trusted, runner, remote, direct_remote, direct_work, config = (root / n for n in
            ('trusted', 'runner', 'remote.git', 'direct.git', 'direct-work', 'gh-config'))
        trusted.mkdir(); remote.mkdir(); direct_remote.mkdir(); stage.mkdir(); config.mkdir()
        git(trusted, 'init', '--quiet', '-b', 'develop')
        (trusted / 'base.txt').write_text('base\n', encoding='ascii', newline='\n')
        git(trusted, 'add', 'base.txt')
        commit_env = _base_git_environment()
        commit_env.update(GIT_AUTHOR_DATE='2026-10-10T12:00:00+00:00',
                          GIT_COMMITTER_DATE='2026-10-10T12:00:00+00:00')
        subprocess.run(['git', '-C', str(trusted), '-c', 'user.name=Fixture',
            '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'base'],
            check=True, capture_output=True, env=commit_env, timeout=30)
        baseline = git(trusted, 'rev-parse', 'HEAD')
        bundle = root / 'baseline.bundle'
        git(trusted, 'bundle', 'create', str(bundle), 'refs/heads/develop')
        workspaces = {}
        for destination in (remote, direct_remote):
            git(destination, 'init', '--quiet', '--bare')
            git(trusted, 'push', str(destination), 'HEAD:refs/heads/develop')
        # Independent receiver journal measures actual direct Git updates, not a constant.
        receive_journal = root / 'direct-receive.txt'
        install_direct_journal(direct_remote, receive_journal)
        def received():
            return received_updates(receive_journal)
        for key in ('a', 'b', 'direct'):
            path = direct_work if key == 'direct' else runner / 'runs' / (IDENTITY + '-' + key) / 'workspace'
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'clone', '-q', '--no-local', str(trusted), str(path)],
                capture_output=True, check=True, env=_base_git_environment(), timeout=30)
            git(path, 'checkout', '-qb', 'run-branch' if key != 'b' else 'api-branch')
            git(path, 'config', 'core.autocrlf', 'false')
            workspaces[key] = path
        git(direct_work, 'remote', 'set-url', 'origin', str(direct_remote))
        for key in ('a', 'b'):
            git(workspaces[key], 'remote', 'remove', 'origin')
            configure_remote(workspaces[key], REPOSITORY)
        direct_env = isolated_environment(config)
        direct_env.update({key: value for key, value in commit_env.items()
                           if key.startswith(('GIT_AUTHOR_DATE', 'GIT_COMMITTER_DATE'))})
        direct = Provider(lambda branch: git(direct_remote, 'rev-parse', 'refs/heads/' + branch)
                          if branch == 'run-branch' else baseline)
        mediated = Provider(lambda branch: git(remote, 'rev-parse', 'refs/heads/' + branch)
                            if branch == 'run-branch' else baseline)
        direct_http = direct.serve(); servers.append(direct_http)
        def git_provider(args, **options):
            expected = 'https://github.com/' + REPOSITORY + '.git'
            rewritten = [str(remote) if item == expected else item for item in args]
            if expected in args and any(item in args for item in ('push', 'fetch', 'ls-remote')):
                op = next(item for item in ('push', 'fetch', 'ls-remote') if item in args)
                git_calls.append({'command': op, 'target': args[-1]})
            return subprocess.run(rewritten, **options)
        store = MediationStore(root / 'effects.sqlite',
            verified_stage_resolver=make_grant_stage_resolver(runner, stage, runner),
            stage_freezer=make_grant_bundle_freezer(runner, stage, runner,
                confirmed_stage_authorizer=lambda grant, snapshot: store.confirmed_stage(grant, snapshot)),
            verified_workflow_classifier=classify_verified_workflow,
            connection_is_current=lambda cid, gen, repo: (cid, gen, repo) == (IDENTITY, 1, REPOSITORY))
        def credential(cid, generation):
            if (cid, generation) != (IDENTITY, 1): raise KeyError('wrong_connection')
            return TOKEN
        transport = GitHubMediatedTransport(
            GitHubGitTransport(REPOSITORY, trusted, baseline, credential,
                               run=git_provider, require_verified_stage=True),
            GitHubRestTransport(REPOSITORY, credential, opener=mediated))
        service = MediationHTTPService(store, transport)
        threading.Thread(target=service.serve, daemon=True).start(); servers.append(service)
        wrappers = prepare_commands(root, REPOSITORY, 'run-branch')
        for key in ('a', 'b'):
            run_id = IDENTITY + '-' + key
            branch = 'run-branch' if key == 'a' else 'api-branch'
            ops = {'git_push', 'git_fetch', 'pr_create', 'pr_update', 'pr_read', 'pr_list',
                   'issue_create', 'issue_list', 'actions_read', 'api_rest_read'}
            grant, token = store.issue(run_id=run_id, invocation_id=run_id + '-invocation',
                repository=REPOSITORY, branch=branch, base_branch='develop', operations=ops,
                ttl_seconds=60, connection_id=IDENTITY, connection_generation=1,
                reviewed_issue_requests={PROPOSAL: REVIEWED_ISSUE})
            grants[key] = grant
            capability = root / ('capability-' + key); capability.write_text(token, encoding='ascii')
            name, launch = 'laomedo-paired-' + secrets.token_hex(8), secrets.token_hex(16)
            containers[key] = {'name': name, 'token': launch, 'run_id': run_id}
            scope = {'repository': REPOSITORY, 'branch': branch, 'base_branch': 'develop',
                     'invocation_id': run_id + '-invocation', 'connection_id': IDENTITY,
                     'connection_generation': 1, 'operations': sorted(ops)}
            record = {'run_id': run_id, 'status': 'running', 'workspace_mode': 'git',
                'git_baseline': baseline, 'github_scope': scope, 'container_ownership': {
                    'name': name, 'launch_token': launch, 'grant_id': grant,
                    'supervised': True, 'cleanup_verified': False}}
            (workspaces[key].parent / 'record.json').write_text(json.dumps(record), encoding='utf8', newline='\n')
            mounts = [(workspaces[key], '/draft', False), (capability, '/run/laomedo/capability', True),
                (wrappers, '/run/laomedo/bin', True),
                (ROOT / 'laomedo/agent_mediation_client.mjs', '/run/laomedo/mediate.mjs', True),
                (ROOT / 'laomedo/agent_gh_adapter.mjs', '/run/laomedo/gh.mjs', True),
                (ROOT / 'laomedo/agent_git_remote.mjs', '/run/laomedo/git-remote.mjs', True)]
            argv = ['docker', 'run', '-d', '--name', name, '--pull=never', '--network=bridge',
                '--label', LABEL_RUN + '=' + run_id, '--label', LABEL_TOKEN + '=' + launch,
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user=10001:10001',
                '--pids-limit=128', '--memory=1g', '--tmpfs=/tmp:rw,noexec,nosuid,size=64m', '--workdir=/draft']
            environment = {'PATH': '/run/laomedo/bin:/usr/local/bin:/usr/bin:/bin',
                'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                'GIT_AUTHOR_DATE': commit_env['GIT_AUTHOR_DATE'], 'GIT_COMMITTER_DATE': commit_env['GIT_COMMITTER_DATE'],
                'LAOMEDO_REPOSITORY': REPOSITORY, 'LAOMEDO_RUN_BRANCH': branch,
                'LAOMEDO_BASE_BRANCH': 'develop', 'LAOMEDO_MEDIATOR_INSTANCE': service.instance,
                'LAOMEDO_MEDIATOR_URL': 'http://host.docker.internal:' + str(service.port) + '/v1/mediate',
                'LAOMEDO_CAPABILITY_FILE': '/run/laomedo/capability'}
            for variable, value in environment.items(): argv += ['--env', variable + '=' + value]
            for src, dst, ro in mounts:
                argv += ['--mount', 'type=bind,source=' + str(src) + ',target=' + dst + (',readonly' if ro else '')]
            launched = command(argv + [GIT_IMAGE_ID, 'sleep', '600'])
            if launched['exit'] != 0: raise RuntimeError('container_launch_failed_no_retry')
        verifier = BundleVerifier(runner, stage, agent_mount=runner, baseline_bundle=bundle,
                                   baseline_sha256=sha256(bundle.read_bytes()).hexdigest())
        worker = threading.Thread(target=verifier.serve, args=(stopped,), daemon=True)
        worker.start(); verifiers.append(worker)
        revoked = set()
        revocation_lock = threading.Lock()
        def renew():
            while not stopped.wait(5):
                with revocation_lock:
                    for key, grant in grants.items():
                        if key in revoked: continue
                        owner = containers[key]
                        state, _ = inspect_exact(owner['name'], owner['run_id'], owner['token'])
                        if state != 'owned' or not store.renew_grant(grant, 60):
                            stopped.set(); return
        threading.Thread(target=renew, daemon=True).start()
        def m(argv, key='a', *, effect=None, body=None, reviewed=True):
            if stopped.is_set(): raise RuntimeError('renewal_or_verifier_stopped')
            args = ['docker', 'exec', '-i']
            if effect:
                args += ['--env=LAOMEDO_EFFECT_ID=' + effect,
                         '--env=LAOMEDO_RECONCILIATION_MARKER=' + MARKER,
                         '--env=LAOMEDO_REVIEWED_PROPOSAL_ID=' + (PROPOSAL if reviewed else 'unreviewed')]
            args += [containers[key]['name'], *argv]
            return command(args, stdin=body.encode() if isinstance(body, str) else body)
        def d(path, method='GET', body=None):
            args = ['gh', 'api', f'http://127.0.0.1:{direct_http.server_port}' + path, '--method', method]
            if body is not None: args += ['--input', '-']
            return command(args, cwd=config, env=direct_env,
                           stdin=json.dumps(body).encode() if body is not None else None)
        def normalized(value):
            if isinstance(value, dict) and 'items' in value: value = value['items']
            if isinstance(value, dict) and 'number' in value:
                selected = {field: value.get(field) for field in ('number', 'title', 'body')}
                if 'head' in value:
                    head = value['head']
                    selected['head'] = {'branch': head.get('branch', head.get('ref')),
                        'repository': head.get('repository', (head.get('repo') or {}).get('full_name')),
                        'sha': head.get('sha')}
                    base = value.get('base')
                    selected['base'] = base.get('ref') if isinstance(base, dict) else base
                return selected
            if isinstance(value, list): return [normalized(item) for item in value]
            return value
        def add(case, med, baseline=None, *, classification='equivalent', key='a', before=None):
            calls_before, writes_before = before or (len(mediated.calls), mediated.writes)
            row = {'case': case, 'run': key, 'run_id': IDENTITY + '-' + key,
                'classification': classification, 'direct': {'exit': baseline['exit'],
                    'normalized': normalized(baseline['value'])} if baseline else None,
                'mediated': {'exit': med['exit'], 'reason': med.get('reason', 'unclassified'),
                             'normalized': normalized(med['value'])},
                'provider_delta': len(mediated.calls) - calls_before,
                'provider_write_delta': mediated.writes - writes_before}
            observation['cases'].append(row)
        def pair(case, argv, path, *, key='a', effect=None, payload=None, stdin=None, method='GET'):
            before = len(mediated.calls), mediated.writes
            med = m(argv, key, effect=effect, body=stdin)
            direct_before = direct.writes
            baseline_result = d(path, method, payload)
            add(case, med, baseline_result, key=key, before=before)
            observation['cases'][-1]['direct_write_delta'] = direct.writes - direct_before
        def deny(case, argv, *, key='a', effect=None, body=None, reviewed=True, kind='unsupported'):
            before = len(mediated.calls), mediated.writes
            add(case, m(argv, key, effect=effect, body=body, reviewed=reviewed),
                classification=kind, key=key, before=before)
        # Actual direct/mediated local Git and deterministic commits.
        local_steps = {'direct': [], 'mediated': []}
        for revision in ('first', 'second'):
            text = revision + ' paired change\n'
            for path in (direct_work, workspaces['a']):
                (path / 'change.txt').write_text(text, encoding='ascii', newline='\n')
            for args in (['status', '--porcelain'], ['diff', '--', 'change.txt'], ['add', 'change.txt'],
                         ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                          'commit', '-qm', revision]):
                med = m(['git', '-c', 'safe.directory=/draft', *args])
                ordinary = command(['git', *args], cwd=direct_work, env=direct_env)
                if med['exit'] or ordinary['exit'] or med['value'] != ordinary['value']:
                    raise ValueError('local_git_difference')
                for key, outcome in (('direct', ordinary), ('mediated', med)):
                    local_steps[key].append({'command': args, 'exit': outcome['exit'],
                        'output_sha256': sha256(json.dumps(outcome['value'], sort_keys=True).encode()).hexdigest()})
            med_commit = m(['git', '-c', 'safe.directory=/draft', 'rev-parse', 'HEAD'])
            direct_commit = command(['git', 'rev-parse', 'HEAD'], cwd=direct_work, env=direct_env)
            if med_commit['value'] != direct_commit['value']: raise ValueError('paired_commit_mismatch')
            med_before = sum(call['command'] == 'push' for call in git_calls)
            direct_before = len(received())
            pushed = m(['git', '-c', 'safe.directory=/draft', 'push', 'origin', 'HEAD:refs/heads/run-branch'])
            ordinary = command(['git', 'push', 'origin', 'HEAD:refs/heads/run-branch'], cwd=direct_work, env=direct_env)
            pushed['value'] = git(remote, 'rev-parse', 'refs/heads/run-branch')
            ordinary['value'] = git(direct_remote, 'rev-parse', 'refs/heads/run-branch')
            add('git_push_' + revision, pushed, ordinary)
            observation['cases'][-1].update(
                git_write_delta=sum(call['command'] == 'push' for call in git_calls) - med_before,
                direct_git_write_delta=len(received()) - direct_before)
        observation['git_local_steps'] = local_steps
        add('git_local', {'exit': 0, 'value': local_steps['mediated']}, {'exit': 0, 'value': local_steps['direct']})
        for branch, case in (('develop', 'git_fetch_base'), ('run-branch', 'git_fetch_run')):
            med = m(['git', '-c', 'safe.directory=/draft', 'fetch', 'origin', branch])
            ordinary = command(['git', 'fetch', 'origin', branch], cwd=direct_work, env=direct_env)
            med['value'] = git(workspaces['a'], 'rev-parse', 'FETCH_HEAD')
            ordinary['value'] = git(direct_work, 'rev-parse', 'FETCH_HEAD')
            add(case, med, ordinary)
        for case, args in (('force_refused', ['--force', 'origin', 'HEAD:refs/heads/run-branch']),
                           ('other_ref_refused', ['origin', 'HEAD:refs/heads/other']),
                           ('multi_ref_refused', ['origin', 'HEAD:refs/heads/run-branch', 'HEAD:refs/heads/other'])):
            before_git = len(git_calls)
            deny(case, ['git', '-c', 'safe.directory=/draft', 'push', *args], kind='denied')
            if len(git_calls) != before_git: raise ValueError('denied_git_reached_provider')
        # Body file is inside .git so it is never staged into the agent's PR.
        initial = MARKER + '\nInitial PR body'
        final = MARKER + '\nFinal checked body'
        (workspaces['a'] / '.git/body.txt').write_text(initial, encoding='utf8', newline='\n')
        pair('pr_create_file', ['gh', 'pr', 'create', '--title', 'Paired PR', '--body-file', '.git/body.txt',
            '--head', 'run-branch', '--base', 'develop'], '/repos/' + REPOSITORY + '/pulls',
            effect='pr-create', method='POST', payload={'title': 'Paired PR', 'body': initial,
                                                     'head': 'run-branch', 'base': 'develop'})
        pair('pr_read', ['gh', 'pr', 'view', '7'], '/repos/' + REPOSITORY + '/pulls/7')
        pair('pr_edit_stdin', ['gh', 'pr', 'edit', '7', '--title', 'Paired PR', '--body-file', '-'],
            '/repos/' + REPOSITORY + '/pulls/7', effect='pr-edit', stdin=final,
            method='PATCH', payload={'title': 'Paired PR', 'body': final, 'base': 'develop'})
        pair('pr_list', ['gh', 'pr', 'list'], '/repos/' + REPOSITORY + '/pulls')
        api_pr = {'title': 'Paired API PR', 'body': initial, 'head': 'api-branch', 'base': 'develop'}
        pair('pr_api_create', ['gh', 'api', 'repos/' + REPOSITORY + '/pulls', '--method', 'POST', '--input', '-'],
            '/repos/' + REPOSITORY + '/pulls', key='b', effect='api-create',
            stdin=json.dumps(api_pr), payload=api_pr, method='POST')
        pair('issue_read', ['gh', 'issue', 'view', '9'], '/repos/' + REPOSITORY + '/issues/9')
        pair('issue_list', ['gh', 'issue', 'list'], '/repos/' + REPOSITORY + '/issues')
        pair('issue_create', ['gh', 'issue', 'create', '--title', REVIEWED_ISSUE['title'], '--body-file', '-'],
            '/repos/' + REPOSITORY + '/issues', effect='issue-create', stdin=REVIEWED_ISSUE['body'],
            payload={key: REVIEWED_ISSUE[key] for key in ('title', 'body')}, method='POST')
        pair('graphql_read', ['gh', 'api', 'graphql', '--method', 'POST', '--input', '-'],
            '/graphql', payload=GRAPHQL_INPUT, stdin=json.dumps(GRAPHQL_INPUT), method='POST')
        pair('actions_list', ['gh', 'run', 'list'], '/repos/' + REPOSITORY + '/actions/runs')
        pair('actions_job', ['gh', 'api', 'repos/' + REPOSITORY + '/actions/jobs/21'],
            '/repos/' + REPOSITORY + '/actions/jobs/21')
        pair('rest_get', ['gh', 'api', 'repos/' + REPOSITORY + '/issues/9'], '/repos/' + REPOSITORY + '/issues/9')
        negatives = [
            ('wrong_repository', ['pr', 'view', '7', '--repo', 'other/repo']),
            ('wrong_base', ['pr', 'create', '--title', 'T', '--body', initial, '--head', 'run-branch', '--base', 'other']),
            ('wrong_pr', ['pr', 'edit', '999', '--title', 'T', '--body', initial]),
            ('arbitrary_write', ['api', 'repos/' + REPOSITORY + '/issues', '--method', 'DELETE']),
            ('api_default_post', ['api', 'repos/' + REPOSITORY + '/pulls', '--input', '-']),
            ('credential_export', ['auth', 'token']), ('auth_login', ['auth', 'login']),
            ('alias', ['alias', 'set', 'x', 'api']), ('extension', ['extension', 'list']),
            ('paging', ['issue', 'list', '--limit', '100'])]
        for case, argv in negatives:
            deny(case, ['gh', *argv], effect='negative-' + case, body='{}', kind='denied' if case.startswith('wrong_') else 'unsupported')
        issue_args = ['gh', 'issue', 'create', '--title', REVIEWED_ISSUE['title'], '--body-file', '-']
        deny('unreviewed_issue', issue_args, effect='unreviewed', body=REVIEWED_ISSUE['body'], reviewed=False, kind='denied')
        deny('edited_issue', issue_args, effect='edited', body=REVIEWED_ISSUE['body'] + ' edited', kind='denied')
        for case, input_value in [('graphql_mutation', {**GRAPHQL_INPUT, 'query': 'mutation{deleteIssue(input:{}){clientMutationId}}'}),
                ('graphql_crossrepo', {**GRAPHQL_INPUT, 'variables': {'owner': 'other', 'name': 'repo'}}),
                ('graphql_paging', {**GRAPHQL_INPUT, 'query': GRAPHQL_INPUT['query'].replace('first:30', 'first:100')})]:
            deny(case, ['gh', 'api', 'graphql', '--method', 'POST', '--input', '-'], body=json.dumps(input_value))
        deny('api_extra_fields', ['gh', 'api', 'repos/' + REPOSITORY + '/pulls', '--method', 'POST', '--input', '-'],
             key='b', effect='extra', body=json.dumps({**api_pr, 'draft': True}))
        before = len(mediated.calls), mediated.writes
        replay = m(issue_args, effect='issue-create', body=REVIEWED_ISSUE['body'])
        add('confirmed_replay', replay, classification='different-but-authorized', before=before)
        deny('altered_effect', ['gh', 'pr', 'create', '--title', 'Changed valid title', '--body', initial,
             '--head', 'run-branch', '--base', 'develop'], effect='pr-create', kind='denied')
        # A saved read/write snapshot mismatch is injected at the transport read boundary.
        original_open = mediated.open
        changed = {'active': True}
        rest_transport = transport.rest
        def mismatching_open(request, timeout):
            if changed['active'] and request.get_method() == 'GET' and request.full_url.endswith('/pulls/7'):
                response = original_open(request, timeout)
                value = json.loads(response.read()); response.close()
                value['title'] = 'Changed by other writer'; changed['active'] = False
                from experiments.exp100.paired_provider import Response
                return Response(json.dumps(value).encode())
            return original_open(request, timeout)
        class ChangedOpener:
            def open(self, request, timeout): return mismatching_open(request, timeout)
        rest_transport.opener = ChangedOpener()
        # Adapter observes modified title; host's subsequent read sees original and refuses before PATCH.
        before = len(mediated.calls), mediated.writes
        outcome = m(['gh', 'pr', 'edit', '7', '--title', 'T', '--body', final], effect='changed-snapshot')
        add('changed_pr_snapshot', outcome, classification='denied', before=before)
        # Read attempts are allowed; the checker requires zero PATCH/write delta.
        rest_transport.opener = mediated
        mediated.drop_next_patch = True; direct.drop_next_patch = True
        before = len(mediated.calls), mediated.writes
        lost = m(['gh', 'pr', 'edit', '8', '--title', 'Lost response PR', '--body', final], key='b', effect='lost-response')
        direct_before = direct.writes
        direct_lost = d('/repos/' + REPOSITORY + '/pulls/8', 'PATCH', {'title': 'Lost response PR', 'body': final, 'base': 'develop'})
        add('lost_response', lost, direct_lost, classification='unknown', key='b', before=before)
        observation['cases'][-1]['direct_write_delta'] = direct.writes - direct_before
        before = len(mediated.calls), mediated.writes
        # Use identical saved request rather than re-read-and-edit changing the expected snapshot.
        effect = store.effect(IDENTITY + '-b', 'lost-response')
        observation['unknown_effect'] = {'run_id': IDENTITY + '-b', 'effect_id': 'lost-response',
                                        'state': effect['state']}
        request_payload = {'number': 8, 'head': 'api-branch', 'base': 'develop', 'title': 'Lost response PR',
            'body': final, 'marker': MARKER, 'expected': {'title': 'Paired API PR', 'body': initial, 'head_sha': baseline}}
        reply = store.invoke(token=(root / 'capability-b').read_text(), repository=REPOSITORY,
            operation='pr_update', payload=request_payload, effect_id='lost-response', transport=transport)
        add('unknown_replay', {'exit': None, 'value': reply['state']},
            classification='unknown', key='b', before=before)
        observation['cases'][-1]['mediated']['source'] = 'host_saved_request'
        with revocation_lock:
            revoked.add('a')
            store.revoke_run(IDENTITY + '-a')
        deny('revoked_a', ['gh', 'issue', 'list'], kind='denied')
        pair('live_b', ['gh', 'issue', 'list'], '/repos/' + REPOSITORY + '/issues', key='b')
        # Actual inspected env/mount destinations, not just the launch configuration.
        inspected = command(['docker', 'inspect', containers['a']['name']])
        info = inspected['value'][0]
        env_keys = [item.split('=', 1)[0] for item in info['Config']['Env']]
        destinations = [item['Destination'] for item in info['Mounts']]
        capability_readonly = any(item['Destination'] == '/run/laomedo/capability' and not item['RW'] for item in info['Mounts'])
        inventory = {'reusable_credential_present': any(key in env_keys for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GH', 'GH_LAOMEDO')),
            'host_config_present': any('codex' in item or '.config/gh' in item or '.gitconfig' in item for item in destinations),
            'capability_mount_readonly': capability_readonly, 'env_keys': sorted(env_keys),
            'mount_destinations': sorted(destinations)}
        add('credential_inventory', {'exit': inspected['exit'], 'value': inventory}, classification='different-but-authorized')
        observation.update(direct_rest_calls=direct.calls, mediated_rest_calls=mediated.calls,
            git_calls=git_calls, direct_git_receives=received(), direct_write_count=direct.writes + len(received()),
            mediated_write_count=mediated.writes + sum(call['command'] == 'push' for call in git_calls),
            direct_provider_state={'prs': direct.prs, 'issues': direct.issues},
            mediated_provider_state={'prs': mediated.prs, 'issues': mediated.issues})
        observation['grants'] = [{'run_id': IDENTITY + '-' + key, 'grant_id': grant,
                                  'connection_id': IDENTITY, 'connection_generation': 1}
                                 for key, grant in grants.items()]
        with sqlite3.connect(root / 'effects.sqlite') as db:
            db.row_factory = sqlite3.Row
            observation['effect_records'] = [dict(row) for row in db.execute(
                'SELECT run_id,effect_id,operation,state,grant_id,invocation_id FROM effects ORDER BY run_id,effect_id')]
    except Exception as failure:
        observation['failure_class'] = type(failure).__name__
        observation['failure_category'] = str(failure) if isinstance(failure, ValueError) else 'execution_incomplete_no_retry'
    finally:
        cleanup_started = time.monotonic()
        stopped.set()
        revoked_grants = []
        for key, grant in grants.items():
            try:
                store.revoke_run(IDENTITY + '-' + key)
                revoked_grants.append({'run': key, 'verified': store.renew_grant(grant, 60) is False})
            except Exception:
                revoked_grants.append({'run': key, 'verified': False})
        reports = []
        for key, owner in containers.items():
            try:
                verified, _ = cleanup_exact(owner['name'], owner['run_id'], owner['token'])
                reports.append({'run': key, 'verified': verified})
            except Exception: reports.append({'run': key, 'verified': False})
        for worker in verifiers: worker.join(timeout=30)
        stage_ok, stage_reports = stage_cleanup(stage, verifiers[0] if verifiers else None)
        for server in servers:
            if isinstance(server, MediationHTTPService): server.close()
            else: server.shutdown(); server.server_close()
        cleanup_elapsed = time.monotonic() - cleanup_started
        observation.update(cleanup_reports=reports, stage_cleanup_reports=stage_reports,
            grant_cleanup_reports=revoked_grants,
            cleanup_elapsed_seconds=cleanup_elapsed,
            cleanup_verified=len(reports) == 2 and len(revoked_grants) == 2 and
                all(row['verified'] for row in reports + revoked_grants) and stage_ok and cleanup_elapsed <= 30)
        # Preserve partial journals even if an earlier command timed out or failed.
        observation['mediated_rest_calls'] = list(mediated.calls) if mediated else []
        observation['direct_rest_calls'] = list(direct.calls) if direct else []
        observation['git_calls'] = list(git_calls)
        if 'failure_class' not in observation:
            try: check(observation); observation['result'] = 'passed'
            except Exception as failure:
                observation.update(failure_class=type(failure).__name__, failure_category=str(failure))
        with (private / (IDENTITY + '.json')).open('x', encoding='utf8', newline='\n') as file:
            json.dump(observation, file, indent=2, sort_keys=True); file.write('\n')
    return observation


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-state', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--review-record', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.private_state, args.source_sha, args.review_record), sort_keys=True))
