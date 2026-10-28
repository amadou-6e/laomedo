import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import request; from urllib import error

from laomedo.skills.registry.store import SkillStore; from laomedo.skills.registry.errors import SkillStoreError; from laomedo.skills.registry.errors import ConflictError
from laomedo.skills.operations.service import SkillOperations; from laomedo.skills.operations.utils import proposal
from laomedo.skills.operations.server import SkillOperationServer as server


class SkillOperationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root/'source'
        (source/'rules').mkdir(parents=True)
        self.original = '---\nname: internal-test\ndescription: Internal unit fixture.\n---\n'
        (source/'SKILL.md').write_bytes(self.original.encode())
        (source/'rules/one.md').write_bytes(b'original\n')
        self.store = SkillStore(self.root/'registry')
        self.initial = self.store.import_skill('internal-test', source)
        self.policy = {'policy_id': 'test-policy', 'revision_id': '1',
            'allowed_paths': ['SKILL.md', 'rules/one.md', 'rules/two.md'],
            'allowed_suffixes': ['.md'], 'allow_new_files': True, 'allow_deletions': True,
            'allow_scripts': False, 'allow_dependencies': False, 'allow_assets': False,
            'required_frontmatter': ['name', 'description'], 'permitted_validation_commands': [],
            'max_files': 8, 'max_file_bytes': 8192}
        self.service = SkillOperations(self.store, self.root/'history.db', {'internal-test': self.policy})
        self.operation = {'action': 'modify', 'message': 'Change two files together', 'files': [
            {'path': 'SKILL.md', 'content': self.original+'\nUpdated.\n'},
            {'path': 'rules/one.md', 'content': 'updated\n'}]}

    def prepare(self, revision=None, commit=''):
        return self.service.prepare('internal-test', revision or self.initial['revision_id'], commit)

    def test_prepare_does_not_embed_viewer_image_data_in_agent_snapshot(self):
        source = self.root / "source"
        (source / "image.png").write_bytes(b"\x89PNG\r\n\x1a\ninternal-control")
        record = self.store.import_skill("image-test", source)
        service = SkillOperations(self.store, self.root / "image-history.db", {"image-test": self.policy})
        snapshot = service.prepare("image-test", record["revision_id"])["snapshot"]
        image = next(file for file in snapshot["files"] if file["path"] == "image.png")
        self.assertEqual(image["kind"], "binary")
        self.assertIsNone(image["text"])
        self.assertNotIn("image_data_url", json.dumps(snapshot))

    def test_atomic_multifile_revision_and_replay(self):
        reservation = self.prepare()
        result = self.service.apply(reservation['ticket'], self.operation)
        self.assertEqual(result['commit']['files'], ['SKILL.md', 'rules/one.md'])
        self.assertEqual(result['commit']['parent_commit'], reservation['base_commit'])
        self.assertEqual(self.store.revision('internal-test'), self.initial)
        self.assertEqual(self.service.apply(reservation['ticket'], self.operation), result)
        self.assertFalse(result['promotion_performed'])
        self.assertIn('updated', result['commit']['patch'])
        history = self.service.history('internal-test', result['skill']['revision_id'])
        self.assertEqual(len(history['commits']), 2)
        self.assertEqual(history['commits'][0]['commit_id'], result['commit']['commit_id'])

    def test_conflicting_concurrent_edits_do_not_partially_apply(self):
        first, second = self.prepare(), self.prepare()
        self.service.apply(first['ticket'], self.operation)
        with self.assertRaisesRegex(ConflictError, 'skill_base_changed'):
            self.service.apply(second['ticket'], self.operation)
        self.assertEqual(len(self.service.history('internal-test', self.initial['revision_id'])['commits']), 2)

    def test_policy_denies_entire_batch(self):
        reservation = self.prepare()
        operation = copy.deepcopy(self.operation)
        operation['files'].append({'path': 'secret.md', 'content': 'no'})
        with self.assertRaisesRegex(SkillStoreError, 'skill_edit_policy_denied'):
            self.service.apply(reservation['ticket'], operation)
        self.assertEqual(self.store.revision('internal-test'), self.initial)
        self.assertEqual(len(self.service.history('internal-test', self.initial['revision_id'])['commits']), 1)

    def test_revert_has_distinct_commit_but_same_tree(self):
        first = self.service.apply(self.prepare()['ticket'], self.operation)
        reservation = self.prepare(first['skill']['revision_id'], first['commit']['commit_id'])
        reverted = self.service.apply(reservation['ticket'], {'action': 'modify', 'message': 'Revert',
            'files': [{'path': 'SKILL.md', 'content': self.original},
                      {'path': 'rules/one.md', 'content': 'original\n'}]})
        self.assertEqual(reverted['skill']['revision_id'], self.initial['revision_id'])
        self.assertNotEqual(reverted['commit']['commit_id'], reservation['base_commit'])
        self.assertEqual(len(self.service.history('internal-test', self.initial['revision_id'])['commits']), 3)
        with self.assertRaises(ConflictError):
            self.prepare()

    def test_path_aliases_and_model_authority_rejected(self):
        for path in ('../escape.md', 'rules/../escape.md', 'rules\\one.md'):
            with self.assertRaises(ValueError):
                proposal({**self.operation, 'files': [{'path': path, 'content': 'no'}]})
        with self.assertRaises(ValueError):
            proposal({**self.operation, 'run_id': 'model-forged'})
        with self.assertRaises(ValueError):
            proposal({**self.operation, 'files': [{'path': 'a.md', 'content': ''},
                                                {'path': 'A.md', 'content': ''}]})

    def test_replay_conflict_expiry_and_revocation(self):
        reservation = self.prepare()
        self.service.apply(reservation['ticket'], self.operation)
        with self.assertRaises(ConflictError):
            self.service.apply(reservation['ticket'], {**self.operation, 'message': 'different'})
        self.service.policies.clear()
        with self.assertRaisesRegex(ValueError, 'skill_edit_not_authorized'):
            self.service.apply(reservation['ticket'], self.operation)
        self.service.policies['internal-test'] = self.policy
        with self.service.connect() as db:
            db.execute('UPDATE requests SET expires=0')
        with self.assertRaisesRegex(ValueError, 'skill_ticket_expired'):
            self.service.apply(reservation['ticket'], self.operation)

    def test_add_delete_and_history_integrity(self):
        operation = {'action': 'modify', 'message': 'Replace a rule', 'files': [
            {'path': 'rules/one.md', 'content': None}, {'path': 'rules/two.md', 'content': 'new\n'}]}
        result = self.service.apply(self.prepare()['ticket'], operation,
            editor={'kind': 'agent', 'run_id': 'trusted-adapter-run'})
        self.assertEqual(result['commit']['editor']['run_id'], 'trusted-adapter-run')
        with self.service.connect() as db:
            db.execute("UPDATE commits SET record='{}' WHERE id=?", (result['commit']['commit_id'],))
        with self.assertRaisesRegex(ValueError, 'skill_history_integrity_failure'):
            self.service.history('internal-test', result['skill']['revision_id'])

    def test_http_auth_and_exact_shape(self):
        service = server(self.service, 'x'*32, port=0)
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        url = 'http://127.0.0.1:'+str(service.server_port)+'/v1/skill-operations/prepare'
        payload = {'skill_id': 'internal-test', 'revision_id': self.initial['revision_id'], 'commit_id': ''}
        def call(token, body):
            return request.urlopen(request.Request(url, data=json.dumps(body).encode(),
                headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'}), timeout=5)
        with self.assertRaises(error.HTTPError) as failure:
            call('wrong', payload)
        self.assertEqual(failure.exception.code, 401)
        with call('x'*32, payload) as response:
            self.assertIn('ticket', json.load(response))
        with self.assertRaises(error.HTTPError):
            call('x'*32, {**payload, 'policy': self.policy})

    def test_comparison_is_cumulative_from_selected_snapshot_to_pinned_current(self):
        prepared = self.prepare()
        first = self.service.apply(prepared['ticket'], self.operation)
        prepared2 = self.prepare(first['skill']['revision_id'], first['commit']['commit_id'])
        second = self.service.apply(prepared2['ticket'], {'action': 'modify', 'message': 'Add another rule',
            'files': [{'path': 'rules/two.md', 'content': 'another rule\n'}]})
        compared = self.service.compare('internal-test', prepared['base_commit'], second['skill']['revision_id'])
        self.assertEqual(compared['base_revision'], self.initial['revision_id'])
        self.assertEqual(compared['current_revision'], second['skill']['revision_id'])
        self.assertEqual([file['path'] for file in compared['files']], ['SKILL.md', 'rules/one.md', 'rules/two.md'])
        self.assertIn('+another rule\n', compared['patch'])
        self.assertIn('+updated\n', compared['patch'])
        self.assertNotIn('another rule\\n', compared['patch'])
        pinned = self.service.compare('internal-test', prepared['base_commit'], first['skill']['revision_id'])
        self.assertEqual(len(pinned['files']), 2)
        same = self.service.compare('internal-test', first['commit']['commit_id'], first['skill']['revision_id'])
        self.assertEqual(same['files'], [])
        self.assertEqual(same['patch'], '')

    def test_comparison_additions_deletions_and_missing_final_newline(self):
        prepared = self.prepare()
        result = self.service.apply(prepared['ticket'], {'action': 'modify', 'message': 'Replace rule',
            'files': [{'path': 'rules/one.md', 'content': None}, {'path': 'rules/two.md', 'content': 'no final newline'}]})
        compared = self.service.compare('internal-test', prepared['base_commit'], result['skill']['revision_id'])
        self.assertEqual([item['status'] for item in compared['files']], ['deleted', 'added'])
        self.assertIn('\\ No newline at end of file', compared['patch'])
        self.assertIn('--- /dev/null', compared['patch'])
        self.assertIn('+++ /dev/null', compared['patch'])

    def test_comparison_refuses_cross_skill_commit_and_corrupt_current(self):
        prepared = self.prepare()
        with self.assertRaises(SkillStoreError):
            self.service.compare('other-skill', prepared['base_commit'], self.initial['revision_id'])
        folder = self.store._revision_dir('internal-test', self.initial['revision_id'])/'bundle'
        (folder/'SKILL.md').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.service.compare('internal-test', prepared['base_commit'], self.initial['revision_id'])

    def test_comparison_binary_metadata_does_not_export_bytes(self):
        source = self.root/'binary-source'
        source.mkdir()
        (source/'SKILL.md').write_bytes(self.original.encode())
        (source/'asset.pdf').write_bytes(b'\0private-before')
        base = self.store.import_skill('binary-skill', source)
        service = SkillOperations(self.store, self.root/'binary.db', {'binary-skill': self.policy})
        root_commit = service.prepare('binary-skill', base['revision_id'])['base_commit']
        (source/'asset.pdf').write_bytes(b'\0private-after')
        current = self.store._store_revision('binary-skill', source, base['revision_id'])
        result = service.compare('binary-skill', root_commit, current['revision_id'])
        self.assertTrue(result['files'][0]['binary'])
        self.assertIn('Binary files differ', result['patch'])
        self.assertNotIn('private-before', json.dumps(result))
        self.assertNotIn('private-after', json.dumps(result))

    def test_comparison_unicode_separators_do_not_create_false_missing_newlines(self):
        prepared = self.prepare()
        result = self.service.apply(prepared['ticket'], {'action': 'modify', 'message': 'Keep Unicode line content',
            'files': [{'path': 'rules/one.md', 'content': 'first\fmiddle\u2028last\n'}]})
        comparison = self.service.compare('internal-test', prepared['base_commit'], result['skill']['revision_id'])
        self.assertIn('+first\fmiddle\u2028last\n', comparison['patch'])
        self.assertNotIn('\\ No newline at end of file', comparison['patch'])
