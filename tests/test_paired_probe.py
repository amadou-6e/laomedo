"""Development-only paired checker/provider tests. Never runs the one-shot probe."""
from copy import deepcopy
import json
import shutil
import subprocess
import tempfile
import unittest
from experiments.exp100.paired_cases import IDENTITY, REQUIRED, GRAPHQL_INPUT, REFUSALS, check
from hashlib import sha256
from experiments.exp100.paired_provider import Provider
from experiments.exp100.probe_paired import isolated_environment, install_direct_journal, received_updates
from experiments.exp104.probe_active_delivery import git
from pathlib import Path


class PairedProbeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'Git unavailable')
    def test_receiver_journal_measures_actual_updates_not_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); work = root / 'work'; remote = root / 'remote.git'; journal = root / 'receives.txt'
            work.mkdir(); remote.mkdir()
            git(work, 'init', '-q', '-b', 'run-branch'); git(remote, 'init', '-q', '--bare')
            (work / 'f.txt').write_text('fixture\n')
            git(work, 'add', 'f.txt')
            git(work, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
            install_direct_journal(remote, journal)
            commit = git(work, 'rev-parse', 'HEAD')
            git(work, 'push', str(remote), 'HEAD:refs/heads/run-branch')
            git(work, 'push', str(remote), 'HEAD:refs/heads/run-branch')
            self.assertEqual(received_updates(journal), [['0' * 40, commit, 'refs/heads/run-branch']])

    def valid(self):
        # Explicit synthetic test data, not an observation or acceptance result.
        positives = {'git_local', 'git_fetch_base', 'git_fetch_run', 'git_push_first', 'git_push_second',
            'pr_create_file', 'pr_read', 'pr_edit_stdin', 'pr_list', 'pr_api_create', 'issue_read',
            'issue_list', 'issue_create', 'graphql_read', 'actions_list', 'actions_job', 'rest_get', 'live_b'}
        rows = []
        for name in sorted(REQUIRED):
            classification, exit_code = ('equivalent', 0) if name in positives else ('denied', 3)
            if name in {'lost_response', 'unknown_replay'}: classification, exit_code = 'unknown', 4
            if name == 'unknown_replay': exit_code = None
            if name in {'confirmed_replay', 'credential_inventory'}:
                classification, exit_code = 'different-but-authorized', 0
            value = {'reusable_credential_present': False, 'host_config_present': False,
                     'capability_mount_readonly': True} if name == 'credential_inventory' else 'synthetic'
            if name in {'git_push_first', 'git_push_second'}:
                value = ('a' if name == 'git_push_first' else 'b') * 40
            if name == 'unknown_replay': value = 'unknown'
            reason = REFUSALS[name][1] if name in REFUSALS else 'effect_unknown_no_retry'
            if name in REFUSALS: exit_code = REFUSALS[name][0]
            expected_run = 'b' if name in {'pr_api_create', 'lost_response', 'unknown_replay', 'api_extra_fields', 'live_b'} else 'a'
            rows.append({'case': name, 'run': expected_run, 'run_id': IDENTITY + '-' + expected_run,
                'classification': classification, 'direct': {'exit': 0, 'normalized': value},
                'mediated': {'exit': exit_code, 'reason': reason, 'normalized': value,
                             'source': 'host_saved_request' if name == 'unknown_replay' else 'cli'},
                'provider_delta': 0, 'direct_write_delta': 1 if name in
                    {'pr_create_file', 'pr_edit_stdin', 'pr_api_create', 'issue_create', 'lost_response'} else 0,
                'git_write_delta': 1, 'direct_git_write_delta': 1,
                'provider_write_delta': 1 if name in
                    {'pr_create_file', 'pr_edit_stdin', 'pr_api_create', 'issue_create', 'lost_response'} else 0})
        expected = {'pr-create': ('a', 'confirmed', 'pr_create'), 'pr-edit': ('a', 'confirmed', 'pr_update'),
            'issue-create': ('a', 'confirmed', 'issue_create'), 'changed-snapshot': ('a', 'rejected', 'pr_update'),
            'api-create': ('b', 'confirmed', 'pr_create'), 'lost-response': ('b', 'unknown', 'pr_update')}
        for commit in ('a' * 40, 'b' * 40):
            effect = 'native-' + sha256(('example/disposable\nrun-branch\n' + commit).encode()).hexdigest()
            expected[effect] = ('a', 'confirmed', 'git_push')
        records = [{'effect_id': effect, 'run_id': IDENTITY + '-' + run,
                    'grant_id': 'synthetic-grant-' + run, 'state': state, 'operation': operation}
                   for effect, (run, state, operation) in expected.items()]
        return {'identity': IDENTITY, 'cases': rows, 'cleanup_verified': True,
                'direct_write_count': 7, 'mediated_write_count': 7, 'effect_records': records,
                'unknown_effect': {'run_id': IDENTITY + '-b', 'effect_id': 'lost-response', 'state': 'unknown'},
                'direct_git_receives': [['0' * 40, 'a' * 40, 'refs/heads/run-branch'],
                                        ['a' * 40, 'b' * 40, 'refs/heads/run-branch']],
                'grants': [{'run_id': IDENTITY + '-' + run, 'grant_id': 'synthetic-grant-' + run}
                           for run in ('a', 'b')]}

    def test_checker_negative_controls(self):
        accepted = self.valid(); check(accepted)
        mutations = []
        omitted = deepcopy(accepted); omitted['cases'].pop(); mutations.append(omitted)
        repeated = deepcopy(accepted); repeated['cases'].append(repeated['cases'][0]); mutations.append(repeated)
        wrong_run = deepcopy(accepted); wrong_run['cases'][0]['run_id'] = 'other'; mutations.append(wrong_run)
        false_equivalent = deepcopy(accepted)
        next(row for row in false_equivalent['cases'] if row['case'] == 'graphql_read')['mediated']['normalized'] = 'wrong'
        mutations.append(false_equivalent)
        missing_positive = deepcopy(accepted)
        next(row for row in missing_positive['cases'] if row['case'] == 'graphql_read')['classification'] = 'different-but-authorized'
        mutations.append(missing_positive)
        revoked = deepcopy(accepted)
        next(row for row in revoked['cases'] if row['case'] == 'revoked_a')['provider_write_delta'] = 1
        mutations.append(revoked)
        replay = deepcopy(accepted)
        next(row for row in replay['cases'] if row['case'] == 'unknown_replay')['provider_delta'] = 1
        mutations.append(replay)
        cleanup = deepcopy(accepted); cleanup['cleanup_verified'] = False; mutations.append(cleanup)
        credential = deepcopy(accepted)
        next(row for row in credential['cases'] if row['case'] == 'credential_inventory')['mediated']['normalized']['reusable_credential_present'] = True
        mutations.append(credential)
        wrong_grant = deepcopy(accepted); wrong_grant['effect_records'][0]['grant_id'] = 'other-grant'; mutations.append(wrong_grant)
        wrong_effect_run = deepcopy(accepted); wrong_effect_run['effect_records'][0]['run_id'] = IDENTITY + '-b'; mutations.append(wrong_effect_run)
        wrong_state = deepcopy(accepted); wrong_state['effect_records'][0]['state'] = 'unknown'; mutations.append(wrong_state)
        omitted_effect = deepcopy(accepted); omitted_effect['effect_records'].pop(); mutations.append(omitted_effect)
        duplicate_effect = deepcopy(accepted); duplicate_effect['effect_records'].append(duplicate_effect['effect_records'][0]); mutations.append(duplicate_effect)
        balanced_writes = deepcopy(accepted)
        next(row for row in balanced_writes['cases'] if row['case'] == 'pr_create_file')['provider_write_delta'] = 0
        next(row for row in balanced_writes['cases'] if row['case'] == 'pr_edit_stdin')['provider_write_delta'] = 2
        mutations.append(balanced_writes)
        wrong_reason = deepcopy(accepted)
        next(row for row in wrong_reason['cases'] if row['case'] == 'altered_effect')['mediated']['reason'] = 'mediator_denied:issue_review_denied'
        mutations.append(wrong_reason)
        cli_crash = deepcopy(accepted)
        next(row for row in cli_crash['cases'] if row['case'] == 'graphql_mutation')['mediated']['exit'] = 1
        mutations.append(cli_crash)
        invented_push_count = deepcopy(accepted); invented_push_count['direct_git_receives'].pop(); mutations.append(invented_push_count)
        for invalid in mutations:
            with self.subTest(invalid=mutations.index(invalid)), self.assertRaises(ValueError): check(invalid)

    @unittest.skipUnless(shutil.which('gh'), 'GitHub CLI unavailable')
    def test_direct_fixed_graphql_post_is_a_synthetic_read(self):
        provider = Provider(lambda _: 'a' * 40)
        server = provider.serve()
        try:
            with tempfile.TemporaryDirectory() as folder:
                result = subprocess.run(['gh', 'api', f'http://127.0.0.1:{server.server_port}/graphql',
                    '--method', 'POST', '--input', '-'], input=json.dumps(GRAPHQL_INPUT).encode(),
                    env=isolated_environment(folder), cwd=folder, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout)['data']['repository']['issues']['nodes'][0]['number'], 9)
                self.assertEqual(provider.calls, [{'method': 'POST', 'path': '/graphql', 'write': False}])
                self.assertEqual(provider.writes, 0)
        finally:
            server.shutdown(); server.server_close()

    def test_budget_and_exact_query_refusals(self):
        provider = Provider(lambda _: 'a' * 40, attempt_cap=1)
        code, _ = provider.handle('POST', '/graphql', {'query': 'mutation{}'}, 'Bearer synthetic-paired-host-only')
        self.assertEqual(code, 422)
        self.assertEqual(provider.writes, 0)
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            provider.handle('GET', '/repos/example/disposable/issues', None, 'Bearer synthetic-paired-host-only')
