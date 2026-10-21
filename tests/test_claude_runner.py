"""Internal controls only: simulated CLI receipts are not live acceptance."""
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_local_runner as controls
from laomedo.claude_runner import ClaudeRunner, CLI_VERSION, command, terminal_result, cli_environment
from laomedo.local_runner import RunnerError
from laomedo.output_contract import requirements


class ClaudeRunnerTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
