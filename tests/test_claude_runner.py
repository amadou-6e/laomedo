"""Internal controls only: simulated CLI receipts are not live acceptance."""
import json
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4

import test_local_runner as controls
from laomedo.agents.providers.claude.runner import ClaudeRunner; from laomedo.agents.providers.claude.constants import CLI_VERSION; from laomedo.agents.providers.claude.utils import command; from laomedo.agents.providers.claude.utils import terminal_result; from laomedo.agents.providers.claude.utils import cli_environment; from laomedo.agents.providers.claude.utils import activity_usage
from laomedo.activity.agent_activity.projection import project
from laomedo.agents.runtime.errors import RunnerError
from laomedo.agents.contracts.output import requirements


try:
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False


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
            self.assertEqual(prompt['skills'],[])
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
        self.assertEqual(projected['diagnostics'][0]['evidence'], 'native_stream_and_receipt')

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
            root = self.runner._run_dir(first['run_id'])
            fresh = json.loads((root / 'activity-attempts' / (first['activity_attempt_id'] + '.json')).read_text())
            rows = [json.loads(line) for line in (root / 'activity-events.jsonl').read_text().splitlines()]
            events = [{'raw': {'method': 'capture/usageBaseline', 'threads': fresh['usage_baseline'],
                              'fresh_thread': fresh['fresh_thread']}, 'received_at': rows[0]['received_at']}]
            events += [{'raw': row['event'], 'received_at': row['received_at']}
                       for row in rows[fresh['native_start']:fresh['native_end']]]
            projected = project(events, root_thread=first['thread_id'])
            self.assertEqual(projected['turns'][0]['usage']['inputTokens'], 13)
            self.assertEqual(projected['turns'][0]['usage']['outputTokens'], 5)
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
        self.assertEqual(projected['turns'][0]['usage']['inputTokens'], 13)
        self.assertEqual(projected['turns'][0]['usage']['outputTokens'], 5)
        self.assertEqual(result['effective_model'], 'claude-test')
        self.assertEqual(len(projected['turns']), 1)

    def setUp(self):
        controls.LocalRunnerTests.setUp(self)
        runtime = SimpleNamespace(profile='laomedo-claude-unit', image_id='sha256:'+'b'*64)
        self.runner = ClaudeRunner(self.root.parent / (self.root.name + '-claude'),
            self.runner.store.root, self.source, container=runtime)
        self.addCleanup(lambda: __import__('shutil').rmtree(self.runner.state, ignore_errors=True))
        self.auth = patch.object(self.runner, '_check_auth', return_value='sha256:' + 'a' * 64)
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.catalog = patch.object(self.runner, 'model_catalog', return_value={
            'models':[{'id': key, 'resolved_model':'claude-'+key, 'efforts':['low','medium','high','xhigh','max']}
                      for key in ('sonnet','opus','haiku')], 'account_availability':'cli_reported', 'submitted_turns':0})
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        self.runner._catalog_cached = (time.monotonic(), self.runner.model_catalog())
        self.payload = {"task": "Read skill", "model": "sonnet", "effort": "low",
            "skill_ref": {"skill_id": "sample", "revision_id": self.revision['revision_id'],
                          "tree_hash": self.revision['tree_hash']}}

    def test_telemetry_attempt_boundaries_exclude_prior_resume_records(self):
        def native(root, record, prompt, flag, *, resume):
            with (root / 'otel-events.jsonl').open('a') as out:
                out.write('{}\n' * (2 if resume else 3))
            return {"type":"result", "subtype":"success", "is_error":False,
                    "session_id":record['thread_id'], "result":"done"}
        with patch.object(self.runner, '_invoke', side_effect=native):
            first = self.runner.start(self.payload)
            root = self.runner._run_dir(first['run_id'])
            before = json.loads((root/'activity-attempts'/(first['activity_attempt_id']+'.json')).read_text())
            resumed = self.runner.resume(first['run_id'],'continue', expected_post_run_hash=first['post_run_hash'],
                expected_thread_id=first['thread_id'],model='sonnet',effort='low')
            after = json.loads((root/'activity-attempts'/(resumed['activity_attempt_id']+'.json')).read_text())
        self.assertEqual((before['otel_start'],before['otel_end']),(0,3))
        self.assertEqual((after['otel_start'],after['otel_end']),(3,5))

    @unittest.skipUnless(OBSERVABILITY_AVAILABLE,"observability optional dependencies are not installed")
    def test_successful_native_receipt_without_exports_preserves_result_and_warns(self):
        import io; import threading
        from unittest.mock import Mock
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()),active_host_turn=str(uuid4()))
        self.runner.container.lease = Mock(return_value=SimpleNamespace(finish=lambda:None,stop_heartbeats=lambda:None))
        self.runner.container.prefix = Mock(return_value=[])
        self.runner.container.bounded_command = Mock(return_value=[])
        root = self.runner._run_dir(record['run_id'])
        receipt = {"type":"result","subtype":"success","session_id":record['thread_id'],"result":"done","is_error":False}
        process = SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO((json.dumps(receipt)+'\n').encode()),
                                  returncode=0,wait=lambda **kwargs:0,poll=lambda:0)
        with patch('laomedo.host.leases.utils.cleanup_exact',return_value=(True,'absent')), \
             patch('subprocess.Popen',return_value=process):
            result = self.runner._invoke(root,record,'task',threading.Event(),resume=False)
        self.assertEqual(result['result'],'done')
        self.assertEqual(record['telemetry_capture']['error_category'],'claude_telemetry_capture_failed')
        self.assertEqual(record['telemetry_capture']['records'],0)
        self.assertFalse(list(root.glob('telemetry-environment-*')))
        self.assertFalse(list(root.glob('command-capability-*')))

    @unittest.skipUnless(OBSERVABILITY_AVAILABLE,"observability optional dependencies are not installed")
    def test_unexpected_receiver_cleanup_failure_preserves_native_result(self):
        import io; import threading
        from unittest.mock import Mock
        from laomedo.activity.claude.telemetry import ClaudeTelemetry
        original_close=ClaudeTelemetry.close
        def broken_close(receiver):
            original_close(receiver)
            raise ValueError('private cleanup detail')
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()),active_host_turn=str(uuid4()))
        self.runner.container.lease = Mock(return_value=SimpleNamespace(finish=lambda:None,stop_heartbeats=lambda:None))
        self.runner.container.prefix = Mock(return_value=[])
        self.runner.container.bounded_command = Mock(return_value=[])
        root = self.runner._run_dir(record['run_id'])
        receipt = {"type":"result","subtype":"success","session_id":record['thread_id'],"result":"done","is_error":False}
        process = SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO((json.dumps(receipt)+'\n').encode()),
                                  returncode=0,wait=lambda **kwargs:0,poll=lambda:0)
        with patch('laomedo.host.leases.utils.cleanup_exact',return_value=(True,'absent')), \
             patch('subprocess.Popen',return_value=process), \
             patch.object(ClaudeTelemetry,'close',broken_close):
            result = self.runner._invoke(root,record,'task',threading.Event(),resume=False)
        self.assertEqual(result['result'],'done')
        self.assertEqual(record['telemetry_capture']['error_category'],'claude_telemetry_cleanup_unconfirmed')
        self.assertEqual(record['telemetry_capture']['records'],0)
        self.assertFalse(list(root.glob('telemetry-environment-*')))
        self.assertFalse(list(root.glob('command-capability-*')))

    def test_capture_warning_preserves_completed_snapshot_and_resume_and_prior_boundary(self):
        def native(root, record, prompt, flag, *, resume):
            if not resume:record['telemetry_capture']['error_category']='claude_telemetry_capture_failed'
            return {"type":"result","subtype":"success","is_error":False,"session_id":record['thread_id'],"result":"done"}
        with patch.object(self.runner,'_invoke',side_effect=native):
            first=self.runner.start(self.payload)
            root=self.runner._run_dir(first['run_id'])
            old=root/'activity-attempts'/(first['activity_attempt_id']+'.json')
            self.assertEqual(first['status'],'completed');self.assertTrue(first['snapshot_ready'])
            self.assertEqual(json.loads(old.read_text())['capture_error'],'claude_telemetry_capture_failed')
            resumed=self.runner.resume(first['run_id'],'continue',expected_post_run_hash=first['post_run_hash'],expected_thread_id=first['thread_id'],model='sonnet',effort='low')
            current=root/'activity-attempts'/(resumed['activity_attempt_id']+'.json')
            self.assertEqual(resumed['status'],'completed')
            self.assertIsNone(json.loads(current.read_text())['capture_error'])
            self.assertEqual(json.loads(old.read_text())['capture_error'],'claude_telemetry_capture_failed')

    def test_telemetry_start_failure_prevents_this_controller_dispatch(self):
        import threading
        from unittest.mock import Mock
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()),active_host_turn=str(uuid4()))
        self.runner.container.lease = Mock(return_value=SimpleNamespace(finish=lambda:None,stop_heartbeats=lambda:None))
        self.runner.container.prefix = Mock(return_value=[])
        root = self.runner._run_dir(record['run_id'])
        with patch('laomedo.activity.claude.telemetry.ClaudeTelemetry',side_effect=OSError('private detail')), \
             patch('laomedo.host.leases.utils.cleanup_exact',return_value=(True,'absent')), \
             patch('subprocess.Popen') as launch:
            with self.assertRaisesRegex(RunnerError,'^claude_telemetry_start_failed$'):
                self.runner._invoke(root,record,'task',threading.Event(),resume=False)
            launch.assert_not_called()
        self.assertFalse(list(root.glob('command-capability-*')))

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

    def test_cli_confines_native_tools_and_uses_credential_free_command_server(self):
        thread = str(uuid4())
        args = command(sys.executable, 'sonnet', 'low', thread, resume=True)
        self.assertEqual(args[args.index('--tools') + 1], '')
        self.assertIn('--restricted', args)
        self.assertNotIn('Bash', args[args.index('--tools') + 1])
        self.assertEqual(command(None,'sonnet','low',thread,output_only=True)[command(None,'sonnet','low',thread,output_only=True).index('--tools')+1], '')
        self.assertIn('--strict-mcp-config', args)
        self.assertEqual(args[-2:], ['--resume', thread])
        self.assertNotIn('--dangerously-skip-permissions', args)

    def test_fresh_and_resume_keep_provider_skills_and_bound_snapshot(self):
        with self.invoke():
            first = self.runner.start(self.payload)
            self.assertEqual(first['status'], 'completed')
            self.assertEqual(first['provider'], 'claude')
            self.assertEqual(first['skills'][0]['use_evidence'], 'offered')
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
        self.assertEqual(result['attempt_number'], 2)
        self.assertFalse((self.runner.state / 'turn-ledger.json').exists())

    def test_prepared_cancel_is_durable_and_old_budget_cannot_block_dispatch(self):
        prepared = self.runner._prepare(self.payload)
        cancelled = self.runner.cancel(prepared['run_id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        with self.invoke() as invoked:
            cancelled_again = self.runner._execute(prepared['run_id'], self.payload['task'], resume=False)
            self.assertEqual(cancelled_again['status'], 'cancelled')
        invoked.assert_not_called()
        ledger = self.runner.state / 'turn-ledger.json'
        ledger.write_text(json.dumps({'attempted_turns': 500, 'max_authorized_turns': 1}))
        with self.invoke() as invoked:
            refused = self.runner.start(self.payload)
        invoked.assert_called_once()
        self.assertEqual(refused['status'], 'completed')
        self.assertEqual(json.loads(ledger.read_text()), {'attempted_turns': 500, 'max_authorized_turns': 1})

    def test_environment_excludes_host_service_credentials(self):
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'internal-secret',
                'LAOMEDO_RUNNER_TOKEN_FILE': '/private/runner', 'PATH': '/tools'}):
            env = cli_environment()
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('LAOMEDO_RUNNER_TOKEN_FILE', env)
        self.assertEqual(env['PATH'], '/tools')
        self.assertNotIn('ANTHROPIC_API_KEY', env)

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
        with patch.object(self.runner, '_catalog_cached', (time.monotonic(), {'models':[
                {'id':'fable','resolved_model':'claude-fable-test','efforts':['max','xhigh']}]})):
            record=self.runner._prepare({**self.payload,'model':'fable','effort':'max'})
            self.assertEqual(record['requested_effort'],'max')
            with self.assertRaisesRegex(RunnerError,'unsupported_claude_effort'):
                self.runner._prepare({**self.payload,'model':'fable','effort':'low'})


if __name__ == '__main__':
    unittest.main()
