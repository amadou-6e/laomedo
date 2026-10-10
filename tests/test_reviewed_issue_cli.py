"""Development integration controls, not paired campaign evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from laomedo.github_mediation import MediationStore, MediationError
from laomedo.mediation_authority import RunGrantAuthority

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node unavailable')
class ReviewedIssueCliTests(unittest.TestCase):
    def request(self, body='marker reviewed body'):
        script = """import {plan} from './laomedo/agent_gh_adapter.mjs';
        console.log(JSON.stringify(plan(['issue','create','--title','T','--body',process.argv[1]],
          {repository:'example/disposable',effect:'issue-effect',marker:'marker',
           reviewedProposal:'review-1'}).request));"""
        result = subprocess.run(['node', '--input-type=module', '-e', script, body],
                                cwd=ROOT, check=True, capture_output=True, timeout=10)
        return json.loads(result.stdout)

    def test_host_exact_review_hash_controls_native_issue_request(self):
        approved = self.request()
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            store = MediationStore(Path(folder) / 'store.sqlite')
            _, capability = store.issue(run_id='run', invocation_id='invocation',
                repository=approved['repository'], operations={'issue_create'}, ttl_seconds=30,
                reviewed_issue_requests={'review-1': approved['payload']})
            def invoke(payload, effect='issue-effect'):
                return store.invoke(token=capability, repository=approved['repository'],
                    operation='issue_create', payload=payload, effect_id=effect,
                    transport=lambda *args, **kwargs: calls.append(args) or {'number': 7})
            changed = self.request('marker edited after review')['payload']
            with self.assertRaisesRegex(MediationError, 'issue_review_denied'):
                invoke(changed)
            unreviewed = dict(approved['payload'], reviewed_proposal_id='unreviewed')
            with self.assertRaisesRegex(MediationError, 'issue_review_denied'):
                invoke(unreviewed)
            self.assertEqual(calls, [])
            self.assertEqual(invoke(approved['payload'])['state'], 'confirmed')
            self.assertEqual(invoke(approved['payload'])['state'], 'confirmed')
            self.assertEqual(len(calls), 1)
            store.revoke_run('run')
            with self.assertRaisesRegex(MediationError, 'grant_unavailable'):
                invoke(approved['payload'], 'new-effect')
            self.assertEqual(len(calls), 1)

    def test_default_authority_scope_is_not_widened(self):
        with tempfile.TemporaryDirectory() as folder:
            authority = RunGrantAuthority(Path(folder) / 'authority.sqlite')
            with self.assertRaisesRegex(MediationError, 'authorization_invalid'):
                authority.approve(invocation_id='i', repository='example/disposable',
                    branch='b', operations={'issue_create'}, reviewed_by='user')
