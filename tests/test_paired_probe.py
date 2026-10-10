"""Development-only paired checker/provider tests. Never runs the one-shot probe."""
from copy import deepcopy
import json
import shutil
import subprocess
import tempfile
import unittest
from experiments.exp100.paired_cases import IDENTITY, REQUIRED, GRAPHQL_INPUT, check
from experiments.exp100.paired_provider import Provider
from experiments.exp100.probe_paired import isolated_environment


class PairedProbeTests(unittest.TestCase):
    def valid(self):
        # Explicit synthetic test data, not an observation or acceptance result.
        positives = {'git_local', 'git_fetch_base', 'git_fetch_run', 'git_push_first', 'git_push_second',
            'pr_create_file', 'pr_read', 'pr_edit_stdin', 'pr_list', 'pr_api_create', 'issue_read',
            'issue_list', 'issue_create', 'graphql_read', 'actions_list', 'actions_job', 'rest_get', 'live_b'}
        rows = []
        for name in sorted(REQUIRED):
            classification, exit_code = ('equivalent', 0) if name in positives else ('denied', 3)
            if name in {'lost_response', 'unknown_replay'}: classification, exit_code = 'unknown', 4
            if name in {'confirmed_replay', 'credential_inventory'}:
                classification, exit_code = 'different-but-authorized', 0
            value = {'reusable_credential_present': False, 'host_config_present': False,
                     'capability_mount_readonly': True} if name == 'credential_inventory' else 'synthetic'
            rows.append({'case': name, 'run': 'a', 'run_id': IDENTITY + '-a',
                'classification': classification, 'direct': {'exit': 0, 'normalized': value},
                'mediated': {'exit': exit_code, 'normalized': value}, 'provider_delta': 0,
                'provider_write_delta': 1 if name == 'lost_response' else 0})
        return {'identity': IDENTITY, 'cases': rows, 'cleanup_verified': True,
                'direct_write_count': 7, 'mediated_write_count': 7}

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
