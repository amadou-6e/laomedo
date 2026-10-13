"""PR selection and durable effects through real mediation and REST adapters."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit, parse_qs
from laomedo.github_pr_gateway import GitHubPRGateway
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.github_mediation import MediationStore, MediationError


def raw_pr(number, labels, state="open"):
    return {"number": number, "html_url": f"https://github.com/owner/repo/pull/{number}",
            "node_id": f"PR_{number}", "title": f"Change {number}", "body": "Current PR body",
            "state": state, "draft": True, "merged_at": None,
            "updated_at": "2026-10-13T00:00:00Z", "labels": [{"name": x} for x in labels],
            "head": {"ref": "demo", "sha": "a" * 40, "repo": {"full_name": "owner/repo"}},
            "base": {"ref": "main", "repo": {"full_name": "owner/repo"}}}


class FakeGitHub:
    def __init__(self):
        self.prs = {1: raw_pr(1, ["research", "backend"]), 2: raw_pr(2, ["research"]),
                    3: raw_pr(3, ["backend"], "closed")}
        self.writes = []
        self.timeout_after_write = False
        self.reject_labels = False
        self.full_pages = False
        self.before_read = None

    def open(self, call, timeout=15):
        path = urlsplit(call.full_url).path
        query = parse_qs(urlsplit(call.full_url).query)
        method = call.get_method()
        if path.endswith('/labels') and method == 'GET':
            value = [{"name": "backend"}, {"name": "research"}]
        elif path.endswith('/pulls'):
            if self.full_pages:
                page = int(query['page'][0])
                value = [raw_pr(n, ['backend']) for n in range(page * 100, page * 100 + 100)]
            else:
                value = [copy.deepcopy(v) for v in self.prs.values()
                         if query.get('state', ['open'])[0] in {'all', v['state']}]
        else:
            number = int(path.split('/')[-2] if path.endswith('/labels') else path.split('/')[-1])
            if self.before_read and method == 'GET':
                self.before_read(self.prs[number])
            value = copy.deepcopy(self.prs[number])
            if method in {'PATCH', 'PUT'}:
                if method == 'PUT' and self.reject_labels:
                    from urllib.error import HTTPError
                    raise HTTPError(call.full_url, 422, 'dummy-secret', {}, None)
                changes = json.loads(call.data)
                self.writes.append((method, path, changes))
                for key, item in changes.items():
                    value[key] = [{"name": x} for x in item] if key == 'labels' else item
                value['updated_at'] = '2026-10-13T00:01:00Z'
                self.prs[number] = copy.deepcopy(value)
                if self.timeout_after_write:
                    raise TimeoutError('dummy-secret')
                if method == 'PUT':
                    value = value['labels']
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, limit): return json.dumps(value).encode()[:limit]
        return Response()


class LiveGitHubPRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.clock = [100.0]
        self.store = MediationStore(Path(self.temp.name) / 'mediation.db', now=lambda: self.clock[0])
        self.fake = FakeGitHub()
        self.transport = GitHubRestTransport('owner/repo', lambda: 'DUMMY-TOKEN', opener=self.fake)
        _, token = self.store.issue(run_id='run', invocation_id='invoke', repository='owner/repo',
            operations={'pr_node_update'}, target_prs={1: 'main'}, branch='demo', ttl_seconds=60)
        self.binding = {'token': token, 'run_id': 'run', 'repository': 'owner/repo'}
        self.gateway = GitHubPRGateway({'owner/repo': self.transport}, self.store,
                                      lambda ref: self.binding if ref == 'grant' else None)
        self.url = 'https://github.com/owner/repo'

    def execute(self, action='modify', changes=None, request_id='effect', number=1, ref='grant'):
        operation = {'action': action, 'request_id': request_id, 'grant_ref': ref}
        if action == 'modify': operation['changes'] = changes or {'title': 'Updated title'}
        return self.gateway.execute(self.url, [], 'open', number, operation)

    def test_discovery_matches_all_labels_and_state(self):
        self.assertEqual([x['number'] for x in self.gateway.discover(self.url, ['research', 'backend'])['prs']], [1])
        self.assertEqual(len(self.gateway.discover(self.url, [], 'all')['prs']), 3)

    def test_refresh_reads_current_content_and_refuses_stale_filters(self):
        self.fake.prs[1]['body'] = 'Changed'
        self.assertEqual(self.gateway.execute(self.url, [], 'open', 1)['pr']['body'], 'Changed')
        with self.assertRaisesRegex(ValueError, 'no_longer_matches'):
            self.gateway.execute(self.url, ['backend'], 'open', 2)

    def test_modify_and_restart_replay_send_once(self):
        first = self.execute(changes={'title': 'Updated title', 'body': '', 'labels': []})
        self.assertEqual(first['operation']['status'], 'succeeded')
        self.assertEqual(first['pr']['labels'], [])
        self.assertEqual(first['pr']['body'], '')
        self.gateway = GitHubPRGateway({'owner/repo': self.transport}, self.store, lambda _: self.binding)
        self.assertEqual(self.execute(changes={'title': 'Updated title', 'body': '', 'labels': []}), first)
        self.assertEqual(len(self.fake.writes), 2)
        with self.assertRaisesRegex(ValueError, 'operation_conflict'):
            self.execute(changes={'title': 'Other'})

    def test_close_returns_confirmed_pr_outside_original_filter(self):
        result = self.execute('close')
        self.assertEqual(result['operation']['status'], 'succeeded')
        self.assertEqual(result['pr']['state'], 'closed')
        self.assertEqual(self.execute('close'), result)
        self.assertEqual(len(self.fake.writes), 1)

    def test_timeout_retains_unknown_without_resending(self):
        self.fake.timeout_after_write = True
        result = self.execute()
        self.assertEqual(result['operation']['status'], 'unknown')
        self.assertEqual(self.execute(), result)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertNotIn('dummy-secret', json.dumps(result))

    def test_partial_metadata_labels_operation_stays_unknown(self):
        self.fake.reject_labels = True
        result = self.execute(changes={'title': 'Changed', 'labels': []})
        self.assertEqual(result['operation']['status'], 'unknown')
        self.assertEqual(self.execute(changes={'title': 'Changed', 'labels': []}), result)
        self.assertEqual(len(self.fake.writes), 1)

    def test_expired_revoked_foreign_target_and_grant(self):
        self.clock[0] = 200
        self.assertEqual(self.execute()['operation']['status'], 'failed')
        self.clock[0] = 100
        self.assertEqual(self.execute(number=2, request_id='other')['operation']['status'], 'failed')
        with self.assertRaisesRegex(ValueError, 'grant_unavailable'): self.execute(ref='foreign')
        self.store.revoke_run('run')
        self.assertEqual(self.execute(request_id='revoked')['operation']['status'], 'failed')
        self.assertEqual(self.fake.writes, [])

    def test_fork_merged_changed_branch_and_changed_head_refused(self):
        for mutate in (lambda pr: pr['head']['repo'].update(full_name='foreign/fork'),
                       lambda pr: pr.update(merged_at='now'),
                       lambda pr: pr['head'].update(ref='other')):
            self.fake.prs[1] = raw_pr(1, ['backend']); mutate(self.fake.prs[1])
            self.assertEqual(self.execute(request_id=str(len(json.dumps(self.fake.prs[1]))))['operation']['status'], 'failed')
        self.assertEqual(self.fake.writes, [])

    def test_expiry_between_read_and_write_is_rechecked(self):
        def expire(_): self.clock[0] = 200
        self.fake.before_read = expire
        self.assertEqual(self.execute()['operation']['status'], 'failed')
        self.assertEqual(self.fake.writes, [])

    def test_incomplete_discovery_is_refused(self):
        self.fake.full_pages = True
        with self.assertRaisesRegex(ValueError, 'discovery_incomplete'):
            self.gateway.discover(self.url, [])

    def test_missing_target_grant_cannot_be_created(self):
        with self.assertRaises(MediationError):
            self.store.issue(run_id='x', invocation_id='x', repository='owner/repo',
                             operations={'pr_node_update'}, branch='demo', ttl_seconds=60)

    def test_payload_target_override_and_merge_action_refused(self):
        for operation in ({'action':'merge','request_id':'x','grant_ref':'grant'},
                          {'action':'close','request_id':'x','grant_ref':'grant','number':2}):
            with self.assertRaisesRegex(ValueError, 'operation_invalid'):
                self.gateway.execute(self.url, [], 'open', 1, operation)
        self.assertEqual(self.fake.writes, [])
