import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo.local_runner import LocalRunner, RunnerError
from laomedo.skill_store import SkillStore
from laomedo.workspace_skills import remove_owned_tree
from test_local_runner import FakeServer


class WorkspaceSkillGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_CONFIG_GLOBAL': os.devnull}
        skill = self.root/'skill'
        skill.mkdir()
        self.bytes = b'---\r\nname: sample\r\n---\r\nPinned CRLF fixture.\r\n'
        (skill/'SKILL.md').write_bytes(self.bytes)
        self.store = SkillStore(self.root/'skills')
        self.ref = self.store.import_skill('sample', skill)

    def git(self, path, *args):
        return subprocess.check_output(['git', '-C', str(path), *args],
                                       env=self.env, text=True, stderr=subprocess.DEVNULL)

    def runner(self, index=0, transport=FakeServer):
        checkout = self.root/f'checkout-{index}'
        checkout.mkdir()
        self.git(checkout, 'init')
        source = checkout/'source'
        source.mkdir()
        (source/'tracked.txt').write_bytes(b'SOURCE\r\n')
        self.git(checkout, '-c', 'core.autocrlf=false', 'add', 'source/tracked.txt')
        self.git(checkout, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.autocrlf=false', 'commit', '-m', 'fixture')
        (checkout/'.git/info/exclude').unlink(missing_ok=True)
        return LocalRunner(self.root/f'state-{index}', self.store.root, source,
                           transport=transport, check_docker=False, max_model_turns=1)

    def request(self):
        return {'task': 'fixture', 'model': 'test-model', 'effort': 'low',
                'skill_ref': {key: self.ref[key] for key in ('skill_id','revision_id','tree_hash')}}

    def test_two_clean_checkouts_exact_exclusion_and_crlf_bytes(self):
        for index in range(2):
            runner = self.runner(index)
            self.assertEqual(self.git(runner.source, 'status', '--porcelain'), '')
            record = runner._prepare(self.request())
            workspace = runner.state/'runs'/record['run_id']/'workspace'
            self.assertEqual(self.git(workspace, 'status', '--porcelain'), '')
            self.assertEqual((workspace/'.agents/skills/sample/SKILL.md').read_bytes(), self.bytes)
            self.assertEqual(record['skills'][0]['tree_hash'], self.ref['tree_hash'])
            self.assertEqual(record['skill_git_exclusion']['rules'], ['/.agents/skills/sample/'])
            (workspace/'.agents/unrelated.txt').write_text('visible')
            (workspace/'unrelated.txt').write_text('visible')
            status = self.git(workspace, 'status', '--porcelain', '--untracked-files=all')
            self.assertIn('.agents/unrelated.txt', status)
            self.assertIn('unrelated.txt', status)
            self.assertNotIn('SKILL.md', status)
            self.git(workspace, 'add', '-A')
            staged = self.git(workspace, 'diff', '--cached', '--name-only')
            self.assertNotIn('SKILL.md', staged)
            self.assertIn('unrelated.txt', staged)
            self.assertFalse((runner.source.parent/'.git/info/exclude').exists())
            remove_owned_tree(workspace.parent, runner.state)
            self.assertEqual(self.git(runner.source, 'status', '--porcelain'), '')

    def test_tampered_skill_refuses_before_transport_and_turn(self):
        runner = self.runner()
        record = runner._prepare(self.request())
        path = runner.state/'runs'/record['run_id']/'workspace/.agents/skills/sample/SKILL.md'
        path.write_text('changed')
        with patch.object(runner, '_open_server') as server:
            result = runner._execute(record['run_id'], 'fixture', resume=False)
        server.assert_not_called()
        self.assertEqual(result['error_category'], 'materialized_skill_mismatch')
        self.assertEqual(result['turns'], [])

    def test_agent_skill_edit_cannot_publish_completed_snapshot(self):
        class Editing(FakeServer):
            def wait_turn(self, *args):
                result = super().wait_turn(*args)
                (self.evidence/'workspace/.agents/skills/sample/SKILL.md').write_text('changed')
                return result
        runner = self.runner(transport=Editing)
        result = runner.start(self.request())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_category'], 'materialized_skill_mismatch')
        self.assertIsNone(result['post_run_hash'])
        self.assertIsNone(result['answer'])

    def test_changed_exclusion_refuses_before_transport(self):
        runner = self.runner()
        record = runner._prepare(self.request())
        path = runner.state/'runs'/record['run_id']/'workspace/.git/info/exclude'
        path.write_text('*\n')
        with patch.object(runner, '_open_server') as server:
            result = runner._execute(record['run_id'], 'fixture', resume=False)
        server.assert_not_called()
        self.assertEqual(result['error_category'], 'skill_git_exclusion_changed')

    def test_external_git_directory_refused_without_writing_target(self):
        runner = self.runner()
        outside = self.root/'outside'
        outside.mkdir()
        (runner.source/'.git').write_text('gitdir: '+str(outside)+'\n')
        with self.assertRaisesRegex(ValueError, 'workspace_git_metadata_conflict'):
            runner._prepare(self.request())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list((runner.state/'runs').iterdir()), [])

    def test_preparation_cleanup_failure_is_not_reported_clean(self):
        runner = self.runner()
        with patch('laomedo.local_runner.workspace_skills.install', side_effect=RuntimeError), patch(
                'laomedo.local_runner.workspace_skills.remove_owned_tree', side_effect=PermissionError):
            with self.assertRaisesRegex(RunnerError, 'run_preparation_cleanup_unverified'):
                runner._prepare(self.request())
        self.assertTrue(list((runner.state/'runs').iterdir()))
        self.assertEqual(self.git(runner.source, 'status', '--porcelain'), '')

    def test_agent_exclusion_edit_cannot_publish_snapshot(self):
        class Editing(FakeServer):
            def wait_turn(self, *args):
                result = super().wait_turn(*args)
                (self.evidence/'workspace/.git/info/exclude').write_text('*\n')
                return result
        runner = self.runner(transport=Editing)
        result = runner.start(self.request())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_category'], 'skill_git_exclusion_changed')
        self.assertIsNone(result['post_run_hash'])

    def test_linked_parent_refuses_before_any_skill_read(self):
        runner = self.runner()
        record = runner._prepare(self.request())
        with patch('laomedo.workspace_skills._is_link',
                   side_effect=lambda path: path.name == '.agents'), patch(
                'laomedo.workspace_skills.inventory') as read, patch.object(
                runner, '_open_server') as server:
            result = runner._execute(record['run_id'], 'fixture', resume=False)
        read.assert_not_called()
        server.assert_not_called()
        self.assertEqual(result['error_category'], 'unsafe_materialized_skill_path')

    def test_readonly_cleanup_and_outside_path_refusal(self):
        runner = self.runner()
        record = runner._prepare(self.request())
        run = runner.state/'runs'/record['run_id']
        objects = list((run/'workspace/.git/objects').rglob('*'))
        sample = next(path for path in objects if path.is_file())
        sample.chmod(stat.S_IREAD)
        remove_owned_tree(run, runner.state)
        self.assertFalse(run.exists())
        with self.assertRaisesRegex(ValueError, 'cleanup_path_outside_run_state'):
            remove_owned_tree(runner.source, runner.state)
        self.assertTrue(runner.source.exists())

    def test_git_initialization_failure_does_not_dispatch(self):
        runner = self.runner()
        with patch('laomedo.workspace_skills._bounded_git', side_effect=FileNotFoundError), patch.object(
                runner, '_open_server') as server:
            with self.assertRaisesRegex(ValueError, 'workspace_git_initialization_failed'):
                runner.start(self.request())
        server.assert_not_called()
        self.assertEqual(list((runner.state/'runs').iterdir()), [])
