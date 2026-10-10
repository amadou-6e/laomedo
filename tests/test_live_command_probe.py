"""Synthetic development checks only; never invoke the live capture."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from urllib import request

from experiments.exp100.probe_live import (BoundedOpener, DISPOSABLE, PUBLIC, ISSUE, JOB,
    revoke_and_verify, run_overlap, list_fields)
from laomedo.github_mediation import MediationStore
from laomedo.github_rest_transport import ISSUE_GRAPHQL_QUERY


class FakeProvider:
    def __init__(self): self.calls = []
    def open(self, call, timeout):
        self.calls.append((call.full_url, call.get_method()))
        return type('Response', (), {'status': 200})()


class LiveCommandProbeTests(unittest.TestCase):
    def test_real_store_cleanup_path_can_pass_and_refuses_unknown_grant(self):
        with tempfile.TemporaryDirectory() as folder:
            store = MediationStore(Path(folder) / 'store.sqlite')
            grant, _ = store.issue(run_id='fixture', invocation_id='fixture-invocation',
                repository=DISPOSABLE, operations={'issue_list'}, ttl_seconds=60)
            self.assertTrue(revoke_and_verify(store, 'fixture', grant))
            self.assertTrue(revoke_and_verify(store, 'fixture', grant))
            self.assertFalse(revoke_and_verify(store, 'fixture', 'absent'))

    def test_current_listing_not_historical_membership_and_nonvacuous(self):
        def value(*ids): return {'workflow_runs': [{'id': number} for number in ids]}
        self.assertEqual(run_overlap(value(8, 9), value(9, 10)), [9])
        with self.assertRaises(ValueError): run_overlap(value(), value())
        with self.assertRaises(ValueError): run_overlap(value(1), value(2))

    def test_list_comparison_ignores_only_unselected_volatile_fields(self):
        first = {'items': [{'number': 1, 'title': 'title', 'body': 'body', 'state': 'open', 'updated_at': 'before'}]}
        second = deepcopy(first); second['items'][0]['updated_at'] = 'after'
        self.assertEqual(list_fields(first), list_fields(second))
        second['items'][0]['title'] = 'changed'
        self.assertNotEqual(list_fields(first), list_fields(second))

    def test_issue_limit_and_exact_bytes_independent_of_store(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeProvider(); path = Path(folder) / 'journal.json'
            opener = BoundedOpener(path, base=fake)
            def call(body):
                return request.Request('https://api.github.com/repos/' + DISPOSABLE + '/issues',
                    data=json.dumps(body).encode(), method='POST')
            exact = {key: ISSUE[key] for key in ('title', 'body')}
            with self.assertRaisesRegex(ValueError, 'bytes_denied'):
                opener.open(call({**exact, 'title': 'different'}), timeout=1)
            self.assertEqual(fake.calls, [])
            opener.open(call(exact), timeout=1)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(json.loads(path.read_bytes())[0]['state'], 'response')
            with self.assertRaisesRegex(ValueError, 'budget_exhausted'):
                opener.open(call(exact), timeout=1)
            self.assertEqual(len(fake.calls), 1)

    def test_uncertain_write_claimed_before_network_and_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'journal.json'
            class Lost:
                def open(self, call, timeout):
                    self_row = json.loads(path.read_bytes())[0]
                    if self_row['state'] != 'sending': raise AssertionError('not saved first')
                    raise TimeoutError('lost')
            opener = BoundedOpener(path, base=Lost())
            call = request.Request('https://api.github.com/repos/' + DISPOSABLE + '/issues',
                data=json.dumps({key: ISSUE[key] for key in ('title', 'body')}).encode(), method='POST')
            with self.assertRaises(TimeoutError): opener.open(call, timeout=1)
            with self.assertRaisesRegex(ValueError, 'budget_exhausted'): opener.open(call, timeout=1)
            self.assertEqual(len(opener.rows), 1)

    def test_reads_bounded_and_public_write_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeProvider(); opener = BoundedOpener(Path(folder) / 'journal.json', base=fake)
            for url in ('https://evil.invalid/repos/' + DISPOSABLE + '/issues',
                        'https://api.github.com/repos/other/repo/issues',
                        'https://api.github.com/repos/' + PUBLIC + '/issues'):
                with self.assertRaises(ValueError): opener.open(request.Request(url), timeout=1)
            with self.assertRaises(ValueError): opener.open(request.Request(
                'https://api.github.com/repos/' + PUBLIC + '/issues', data=b'{}', method='POST'), timeout=1)
            self.assertEqual(fake.calls, [])
            call = request.Request('https://api.github.com/repos/' + PUBLIC + '/actions/jobs/' + str(JOB))
            for _ in range(80): opener.open(call, timeout=1)
            with self.assertRaisesRegex(ValueError, 'budget_exhausted'): opener.open(call, timeout=1)
            self.assertEqual(len(fake.calls), 80)

    def test_only_fixed_graphql_read_post(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = FakeProvider(); opener = BoundedOpener(Path(folder) / 'journal.json', base=fake)
            body = {'query': ISSUE_GRAPHQL_QUERY, 'variables': dict(zip(('owner', 'name'), DISPOSABLE.split('/')))}
            def call(value):
                return request.Request('https://api.github.com/graphql', data=json.dumps(value).encode(), method='POST')
            changed = deepcopy(body); changed['variables']['owner'] = 'other'
            with self.assertRaises(ValueError): opener.open(call(changed), timeout=1)
            changed = deepcopy(body); changed['query'] = 'mutation { evil }'
            with self.assertRaises(ValueError): opener.open(call(changed), timeout=1)
            opener.open(call(body), timeout=1)
            self.assertEqual(len(fake.calls), 1)


if __name__ == '__main__': unittest.main()
