"""Internal controls only: simulated CLI receipts are not live acceptance."""
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_local_runner as controls
from laomedo.claude_runner import ClaudeRunner, CLI_VERSION, command, terminal_result, cli_environment, activity_usage
from laomedo.agent_activity_projection import project
from laomedo.local_runner import RunnerError
from laomedo.output_contract import requirements


class ClaudeRunnerTests(unittest.TestCase):
    def test_no_skills_produces_empty_prompt_bundle_and_preserves_resume_binding(self):
        payload={key:value for key,value in self.payload.items() if key!='skill_ref'}
        payload['task']='Answer the task without skills'
        with patch.object(self.runner.store,'revision',side_effect=AssertionError('no skill lookup')), self.invoke():
            result=self.runner.start(payload)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['skills'],[])
            self.assertIsNone(result['skill'])
            root=self.runner._run_dir(result['run_id'])
            prompt=json.loads(self.runner._prompt(root,result,payload['task']))
            self.assertEqual(prompt['pinned_skills'],[])
            self.assertEqual(prompt['task'],payload['task'])
            resumed=self.runner.resume(result['run_id'],'continue',expected_post_run_hash=result['post_run_hash'],
                expected_thread_id=result['thread_id'],model='sonnet',effort='low')
            self.assertEqual(resumed['status'],'completed')
            self.assertEqual(resumed['skills'],[])

    def test_catalog_does_not_dispatch_or_claim_model_execution(self):
        before=(self.runner.state/'turn-ledger.json').exists()
        with patch.object(self.runner,'_invoke',side_effect=AssertionError('no native turn')), \
             patch.object(self.runner,'_open_server',side_effect=AssertionError('no Codex RPC')):
            catalog=self.runner.model_catalog()
        self.assertEqual([item['id'] for item in catalog['models']],['sonnet','opus','haiku'])
        self.assertEqual(catalog['account_availability'],'cli_reported')
        self.assertEqual(catalog['submitted_turns'],0)
        self.assertEqual((self.runner.state/'turn-ledger.json').exists(),before)

    def test_activity_usage_and_resume_do_not_double_count_session_totals(self):
        def native(inputs, outputs):
            return {'modelUsage': {'claude-test': {'inputTokens': inputs,
                'outputTokens': outputs, 'cacheReadInputTokens': 30, 'cacheCreationInputTokens': 5}}}
        first, second = activity_usage(native(10, 4)), activity_usage(native(20, 9))
        self.assertEqual(first['inputTokens'], 45)
        self.assertNotIn('reasoningOutputTokens', first)
        def event(value):
            return {'raw': value, 'received_at': '2026-10-23T10:00:00Z'}
        projected = project([event({'method': 'capture/usageBaseline', 'threads': {'session': {'total': first}}}),
            event({'method': 'thread/tokenUsage/updated', 'params': {'threadId': 'session',
                'tokenUsage': {'total': second}}})], root_thread='session')
        self.assertEqual(projected['usage']['inputTokens'], 10)
        self.assertEqual(projected['usage']['outputTokens'], 5)
        self.assertEqual(projected['usage']['cachedInputTokens'], 0)
        self.assertIsNone(projected['cost']['amount'])
        for invalid in [{}, {'modelUsage': {}}, native(True, 1), native(-1, 1)]:
            self.assertIsNone(activity_usage(invalid))

    def test_codex_notification_without_total_preserves_last_measured_usage(self):
        def event(params):
            return {'raw': {'method': 'thread/tokenUsage/updated', 'params': {'threadId': 'session', **params}},
                    'received_at': '2026-10-23T10:00:00Z'}
        first = event({'tokenUsage': {'total': {'inputTokens': 10, 'outputTokens': 5}}})
        result = project([first, event({'tokenUsage': {'last': {'inputTokens': 2}}})], root_thread='session')
        self.assertEqual(result['usage']['inputTokens'], 10)
        result = project([first, event({'tokenUsage': {'total': None},
                          'usage_scope': 'terminal_receipt_unavailable'})], root_thread='session')
        self.assertIsNone(result['usage'])

    def test_activity_contains_prompt_answer_and_unknown_usage_without_guessing(self):
        with self.invoke():
            result = self.runner.start(self.payload)
        root = self.runner._run_dir(result['run_id'])
        receipts = [json.loads(line) for line in (root / 'activity-events.jsonl').read_text().splitlines()]
        # The on-disk envelope is a runner receipt, just as in the HTTP event feed.
        events = [{'raw': value.get('event', value), 'received_at': value['received_at']} for value in receipts]
        projected = project(events, root_thread=result['thread_id'])
        self.assertEqual([lane['item']['type'] for lane in projected['items']], ['userMessage', 'agentMessage'])
        self.assertIn('Read skill', projected['items'][0]['item']['content'][0]['text'])
        self.assertIsNone(projected['usage'])
        self.assertEqual(projected['diagnostics'][0]['evidence'], 'terminal_receipt_only')

    def test_failed_turn_closes_timeline_and_invalidates_usage(self):
        with patch.object(self.runner, '_invoke', side_effect=RunnerError('claude_process_failed')):
            result = self.runner.start(self.payload)
        root = self.runner._run_dir(result['run_id'])
        receipts = [json.loads(line) for line in (root / 'activity-events.jsonl').read_text().splitlines()]
        projected = project([{'raw': value['event'], 'received_at': value['received_at']}
                             for value in receipts], root_thread=result['thread_id'])
        self.assertEqual(projected['turns'][0]['status'], 'failed')
        self.assertIsNotNone(projected['turns'][0]['ended'])
        self.assertIsNone(projected['usage'])

    def test_real_capture_boundary_uses_previous_receipt_as_resume_baseline(self):
        calls = []
        def invoke(root, record, prompt, flag, *, resume):
            calls.append(resume)
            count = len(calls)
            return {'session_id': record['thread_id'], 'result': 'ok',
                    'modelUsage': {'claude-test': {'inputTokens': count * 10,
                        'cacheReadInputTokens': count * 3, 'cacheCreationInputTokens': 0,
                        'outputTokens': count * 5, 'thinkingTokens': 0}}}
        with patch.object(self.runner, '_invoke', side_effect=invoke):
            first = self.runner.start(self.payload)
            result = self.runner.resume(first['run_id'], 'Continue',
                expected_post_run_hash=first['post_run_hash'], expected_thread_id=first['thread_id'],
                model='sonnet', effort='low')
        root = self.runner._run_dir(result['run_id'])
        attempt = json.loads((root / 'activity-attempts' / (result['activity_attempt_id'] + '.json')).read_text())
        rows = [json.loads(line) for line in (root / 'activity-events.jsonl').read_text().splitlines()]
        events = [{'raw': {'method': 'capture/usageBaseline', 'threads': attempt['usage_baseline']},
                   'received_at': rows[0]['received_at']}]
        events += [{'raw': row['event'], 'received_at': row['received_at']}
                   for row in rows[attempt['native_start']:attempt['native_end']]]
        projected = project(events, root_thread=result['thread_id'])
        self.assertEqual(projected['usage']['inputTokens'], 13)
        self.assertEqual(projected['usage']['outputTokens'], 5)
        self.assertEqual(projected['usage']['reasoningOutputTokens'], 0)
        self.assertEqual(result['effective_model'], 'claude-test')
        self.assertEqual(len(projected['turns']), 1)

    def setUp(self):
        controls.LocalRunnerTests.setUp(self)
        with patch('laomedo.claude_runner.subprocess.run', return_value=subprocess.CompletedProcess(
                [], 0, stdout=CLI_VERSION + ' (Claude Code)\n')), \
                patch.object(ClaudeRunner, '_check_auth'):
            self.runner = ClaudeRunner(self.root.parent / (self.root.name + '-claude'),
                self.runner.store.root, self.source, executable=sys.executable, max_model_turns=3)
        self.addCleanup(lambda: __import__('shutil').rmtree(self.runner.state, ignore_errors=True))
        self.auth = patch.object(self.runner, '_check_auth', return_value='sha256:' + 'a' * 64)
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.catalog = patch.object(self.runner, 'model_catalog', return_value={
            'models':[{'id': key, 'resolved_model':'claude-'+key, 'efforts':['low','medium','high','xhigh','max']}
                      for key in ('sonnet','opus','haiku')], 'account_availability':'cli_reported', 'submitted_turns':0})
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        self.payload = {"task": "Read skill", "model": "sonnet", "effort": "low",
            "skill_ref": {"skill_id": "sample", "revision_id": self.revision['revision_id'],
                          "tree_hash": self.revision['tree_hash']}}

    def invoke(self, answer='{"action":"modify"}'):
        def run(root, record, prompt, flag, *, resume):
            return {"type": "result", "subtype": "success", "is_error": False,
                    "session_id": record['thread_id'], "result": answer}
        return patch.object(self.runner, '_invoke', side_effect=run)

    def test_terminal_receipt_requires_exact_session_and_success(self):
        thread = str(uuid4())
        for value in [{"type": "result", "session_id": str(uuid4()), "result": "text"},
                      {"type": "result", "session_id": thread, "is_error": True},
                      {"type": "result", "session_id": thread, "subtype": "error_max_turns"}]:
            with self.assertRaises(RunnerError):
                terminal_result(json.dumps(value), thread)

    def test_cli_disables_tools_customizations_and_preserves_explicit_resume(self):
        thread = str(uuid4())
        args = command(sys.executable, 'sonnet', 'low', thread, resume=True)
        self.assertEqual(args[args.index('--tools') + 1], '')
        self.assertIn('--safe-mode', args)
        self.assertIn('--strict-mcp-config', args)
        self.assertEqual(args[-2:], ['--resume', thread])
        self.assertNotIn('--dangerously-skip-permissions', args)

    def test_fresh_and_resume_keep_provider_skills_and_bound_snapshot(self):
        with self.invoke():
            first = self.runner.start(self.payload)
            self.assertEqual(first['status'], 'completed')
            self.assertEqual(first['provider'], 'claude')
            self.assertEqual(first['skills'][0]['use_evidence'], 'included_in_prompt')
            second = self.runner.resume(first['run_id'], 'Continue',
                expected_post_run_hash=first['post_run_hash'], expected_thread_id=first['thread_id'],
                model='sonnet', effort='low')
        self.assertEqual(second['thread_id'], first['thread_id'])
        self.assertEqual(len(second['turns']), 2)
        self.assertTrue(second['snapshot_ready'])
        (self.runner._run_dir(first['run_id']) / 'workspace/task.txt').write_text('changed')
        with self.assertRaisesRegex(RunnerError, 'workspace_changed_since_snapshot'):
            self.runner.resume(first['run_id'], 'Continue',
                expected_post_run_hash=second['post_run_hash'], expected_thread_id=first['thread_id'],
                model='sonnet', effort='low')

    def test_correction_continues_same_session_once_and_retains_rejection(self):
        pin = requirements({'schema_version': 1, 'fields': [
            {'name': 'action', 'type': 'string', 'required': True, 'checks': {'enum': ['modify']}}]})
        calls = []
        def run(root, record, prompt, flag, *, resume):
            calls.append((record['thread_id'], resume))
            return {'session_id': record['thread_id'], 'result': 'bad JSON' if len(calls) == 1 else '{"action":"modify"}'}
        with patch.object(self.runner, '_invoke', side_effect=run):
            result = self.runner.start({**self.payload, 'output_requirements': pin, 'output_retries': 1})
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['output_validation']['contract_status'], 'accepted')
        self.assertEqual(result['output_correction_count'], 1)
        self.assertEqual(result['turns'][0]['output_validation']['errors'][0]['code'], 'invalid_json')
        self.assertEqual(calls, [(result['thread_id'], False), (result['thread_id'], True)])
        self.assertEqual(json.loads((self.runner.state / 'turn-ledger.json').read_text())['attempted_turns'], 2)

    def test_zero_budget_cannot_dispatch_and_prepared_cancel_is_durable(self):
        prepared = self.runner._prepare(self.payload)
        cancelled = self.runner.cancel(prepared['run_id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        with self.invoke() as invoked:
            with self.assertRaisesRegex(RunnerError, 'run_not_dispatchable'):
                self.runner._execute(prepared['run_id'], self.payload['task'], resume=False)
        invoked.assert_not_called()
        self.runner.max_model_turns = 0
        with self.invoke() as invoked:
            refused = self.runner.start(self.payload)
        invoked.assert_not_called()
        self.assertEqual(refused['error_category'], 'model_turn_cap_reached')

    def test_environment_excludes_host_service_credentials(self):
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'internal-secret',
                'LAOMEDO_RUNNER_TOKEN_FILE': '/private/runner', 'PATH': '/tools'}):
            env = cli_environment()
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('LAOMEDO_RUNNER_TOKEN_FILE', env)
        self.assertEqual(env['PATH'], '/tools')
        self.assertEqual(env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'], '1')

    def test_trailing_data_has_specific_feedback_without_parser_repair(self):
        pin = requirements({'schema_version': 1, 'fields': []})
        with self.invoke('{"action":"modify"}]}'):
            result = self.runner.start({**self.payload, 'output_requirements': pin, 'output_retries': 0})
        self.assertEqual(result['answer'], '{"action":"modify"}]}')
        self.assertEqual(result['output_validation']['errors'][0]['code'], 'trailing_data')
        self.assertEqual(result['evidence_complete'], 'unknown')
        self.assertNotIn('process_cleanup_verified', result)

    def test_invalid_model_effort_or_external_scope_refuse_before_prepare(self):
        for changes in [{'model': '--other'}, {'effort': 'unsupported'},
                        {'github_authorization_ref': 'not allowed'}]:
            with self.assertRaises(RunnerError):
                self.runner._prepare({**self.payload, **changes})

    def test_native_model_effort_pair_is_checked_before_run_is_created(self):
        with self.assertRaisesRegex(RunnerError,'claude_model_required'):
            self.runner._prepare({**self.payload,'model':'claude-not-in-account'})
        with patch.object(self.runner,'model_catalog',return_value={'models':[
                {'id':'fable','resolved_model':'claude-fable-test','efforts':['max','xhigh']}]}):
            record=self.runner._prepare({**self.payload,'model':'fable','effort':'max'})
            self.assertEqual(record['requested_effort'],'max')
            with self.assertRaisesRegex(RunnerError,'unsupported_claude_effort'):
                self.runner._prepare({**self.payload,'model':'fable','effort':'low'})


if __name__ == '__main__':
    unittest.main()
