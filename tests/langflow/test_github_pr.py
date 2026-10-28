import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from lfx.schema import Data; from lfx.schema import Message

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import test_live_github_pr as fixture_tests


class NativeGitHubPRTests(unittest.TestCase):
    def setUp(self):
        fixture_tests.LiveGitHubPRTests.setUp(self)
        spec = importlib.util.spec_from_file_location('native_github_pr', ROOT / 'components/laomedo/github_pr.py')
        self.module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.component = self.module.LaomedoGitHubPR()
        self.component.set(repository_url=self.url, labels=[], state='open', pr_choice='#1 Change 1')
        def request(action, **body):
            return self.gateway.discover(**body) if action == 'discover' else self.gateway.execute(**body)
        self.mock = patch.object(self.module, 'pr_request', side_effect=request).start()
        self.addCleanup(patch.stopall)

    def test_outputs_share_execution_and_reference_drives_downstream(self):
        self.component.set(operation=Data(data={'action':'close','request_id':'once','grant_ref':'grant'}))
        self.component._pre_run_setup()
        self.assertEqual(self.component.pr_output().data['state'], 'closed')
        self.assertEqual(self.component.result_output().data['operation']['status'], 'succeeded')
        self.assertIn('PR:', self.component.task_output().text)
        self.assertEqual(self.mock.call_count, 1)
        self.assertEqual(len(self.fake.writes), 1)

    def test_reference_conflict_never_dispatches(self):
        self.component.set(pr_reference=Data(data={'repository':'owner/repo', 'number':2}))
        self.component._pre_run_setup()
        self.assertEqual(self.component.result_output().data['operation']['error_category'], 'pr_reference_mismatch')
        self.mock.assert_not_called()

    def test_normal_operation_accepts_message_json(self):
        self.component.set(operation=Message(text='{"action":"close","request_id":"message-once","grant_ref":"grant"}'))
        self.component._pre_run_setup()
        self.assertEqual(self.component.result_output().data['operation']['status'],'succeeded')
        self.assertEqual(len(self.fake.writes),1)

    def test_filters_clear_selection_and_refresh_preserves_number(self):
        config = {item.name: item.to_dict() for item in self.component.inputs}
        config = asyncio.run(self.component.update_build_config(config, self.url, 'repository_url'))
        self.assertEqual(len(config['pr_choice']['options']), 2)
        config = asyncio.run(self.component.update_build_config(config, ['research','backend'], 'labels'))
        self.assertEqual(config['pr_choice']['options'], ['#1 Change 1'])
        self.assertEqual(config['pr_choice']['value'], '')
        config['pr_choice']['value'] = '#1 Change 1'
        self.fake.prs[1]['title'] = 'New title'
        config = asyncio.run(self.component.update_build_config(config, '#1 Change 1', 'pr_choice'))
        self.assertEqual(config['pr_choice']['value'], '#1 New title')

    def test_failure_stops_task_and_unknown_is_routable(self):
        self.component.set(operation=Data(data={'action':'close','request_id':'once','grant_ref':'grant'}))
        self.mock.side_effect = TimeoutError('dummy-secret')
        self.component._pre_run_setup()
        self.assertEqual(self.component.task_output().text, '')
        self.assertEqual(self.component.result_output().data['operation']['status'], 'unknown')


if __name__ == '__main__': unittest.main()
