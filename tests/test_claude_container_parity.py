"""Internal controls; actual Docker/agent/graph evidence is recorded separately."""
from importlib.util import find_spec
import json
import threading
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from laomedo.agents.providers.claude.runner import ClaudeRunner; from laomedo.agents.providers.claude.utils import command
from laomedo.agents.providers.claude.container import ClaudeContainer; from laomedo.agents.providers.claude.container import CommandService
from laomedo.activity.agent_activity.projection import project
from laomedo.agents.runtime.errors import RunnerError
from laomedo.agents.handoffs.utils import envelope
import test_claude_runner as controls


class ClaudeContainerParityTests(unittest.TestCase):
    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker runtime; covered by docker-runtime-controls")
    def test_constructor_classifies_images_configuration_and_cleanup(self):
        """Preserve provider codes while using shared typed Docker failures."""
        from unittest.mock import MagicMock
        from py_docker.errors import CleanupUnconfirmedError, ConnectionConfigurationError, DockerOperationError, ImageResolutionError
        cases = (
            ("client", ConnectionConfigurationError("private connection"), "claude_container_configuration_invalid"),
            ("client", DockerOperationError("private daemon"), "claude_container_unavailable"),
            ("image", ImageResolutionError("private inspection"), "claude_container_image_missing"),
            ("receipt", CleanupUnconfirmedError("private receipt"), "container_termination_unverified"),
        )
        for stage, failure, code in cases:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                receipts = root.joinpath("receipts")
                receipts.mkdir()
                receipts.joinpath("claude-pending.json").write_text("internal control", encoding="utf-8")
                client = MagicMock()
                selected = client.return_value.__enter__.return_value
                if stage == "client":
                    client.side_effect = failure
                elif stage == "image":
                    selected.images.resolve.side_effect = failure
                else:
                    selected.sessions.recover.side_effect = failure
                with patch("py_docker.Client", client), patch.object(ClaudeContainer, "check_supervisor"), patch.object(ClaudeContainer, "control") as control:
                    with self.assertRaisesRegex(RunnerError, "^" + code + "$") as caught:
                        ClaudeContainer("local-image", "laomedo-claude-test", root.joinpath("lease"))
                    self.assertNotIn("private", str(caught.exception))
                    control.assert_not_called()

    def setUp(self):
        controls.ClaudeRunnerTests.setUp(self)

    invoke = controls.ClaudeRunnerTests.invoke

    def test_controller_command_is_bounded_inside_container(self):
        runtime = object.__new__(ClaudeContainer)
        runtime.image_id = 'sha256:' + 'a' * 64
        args = runtime.guarded(['claude', '--print'], time.monotonic() + 20)
        self.assertEqual(args[:2], ['python3', '-c'])
        self.assertIn('--kill-after=5s', args[2])
        self.assertEqual(args[-2:], ['claude', '--print'])
        with self.assertRaisesRegex(RunnerError, 'claude_turn_timeout'):
            runtime.guarded(['claude'], time.monotonic() - 1)

    def test_resume_honors_explicit_execution_timeout(self):
        with self.invoke():
            first = self.runner.start(self.payload)
            attempts = self.runner._run_dir(first['run_id']) / 'activity-attempts'
            fresh = json.loads((attempts / (first['activity_attempt_id'] + '.json')).read_text())
            self.assertIs(fresh['fresh_thread'], True)
            resumed = self.runner.resume(first['run_id'], 'continue',
                expected_post_run_hash=first['post_run_hash'], expected_thread_id=first['thread_id'],
                model='sonnet', effort='low', run_timeout_seconds=31)
        self.assertEqual(resumed['turn_timeout'],31)
        self.assertEqual(resumed['turns'][-1]['execution_timeout_seconds'],31)
        continued = json.loads((attempts / (resumed['activity_attempt_id'] + '.json')).read_text())
        self.assertIs(continued['fresh_thread'], False)

    def test_resume_http_validates_and_forwards_execution_timeout(self):
        from laomedo.agents.runtime.serving import RunnerServer as serve
        from urllib import request; from urllib import error
        server = serve(self.runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        run_id = str(uuid4())
        body = {'task':'continue', 'expected_post_run_hash':'sha256:'+'a'*64,
                'expected_thread_id':str(uuid4()), 'model':'sonnet', 'effort':'low',
                'run_timeout_seconds':31}
        def post():
            return request.urlopen(request.Request(
                f'http://127.0.0.1:{server.server_port}/v1/runs/{run_id}/resume',
                data=json.dumps(body).encode(), headers={'Content-Type':'application/json',
                    'Authorization':'Bearer '+self.runner.api_token}),timeout=10)
        with patch.object(self.runner, '_mirror_host_login') as mirror, \
             patch.object(self.runner, 'resume', return_value={'status':'completed'}) as resume:
            with post() as response:
                self.assertEqual(json.load(response)['status'],'completed')
            mirror.assert_called_once_with(minimum_validity_seconds=31)
            self.assertEqual(resume.call_args.kwargs['run_timeout_seconds'],31)
            mirror.reset_mock();resume.reset_mock()
            for invalid in (0,True,86401,'31'):
                body['run_timeout_seconds']=invalid
                with self.assertRaises(error.HTTPError) as caught:
                    post()
                self.assertEqual(json.load(caught.exception)['error_category'],'claude_turn_timeout_invalid')
            mirror.assert_not_called();resume.assert_not_called()

    def test_stream_and_native_receipts_keep_thinking_and_text_distinct_without_duplicates(self):
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()), active_host_turn=str(uuid4()))
        root = self.runner._run_dir(record['run_id'])
        def stream(value):
            self.runner._native_event(root, record, {'type':'stream_event', 'event':value})
        stream({'type':'message_start','message':{'id':'native-message'}})
        for index, kind, field, text in [(0,'thinking','thinking','considering'), (1,'text','text','final answer')]:
            stream({'type':'content_block_start','index':index,'content_block':{'type':kind,field:text}})
            stream({'type':'content_block_stop','index':index})
            # Native CLI receipts contain a single block even when stream index >0.
            self.runner._native_event(root, record, {'type':'assistant','message':{
                'id':'native-message','content':[{'type':kind,field:text}]}})
        rows=[json.loads(line) for line in (root/'activity-events.jsonl').read_text().splitlines()]
        result=project([{'raw':row['event'],'received_at':row['received_at']} for row in rows])
        self.assertEqual(len(result['items']),2)
        self.assertFalse(any(item.get('conflicting_receipts') for item in result['items']))
        self.assertEqual(record['_last_streamed_text'],'final answer')

    def test_native_receipt_before_block_stop_reuses_live_text_identity(self):
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()), active_host_turn=str(uuid4()))
        root = self.runner._run_dir(record['run_id'])
        def stream(value):
            self.runner._native_event(root, record, {'type': 'stream_event', 'event': value})
        stream({'type': 'message_start', 'message': {'id': 'native-message'}})
        for index, kind, field, text in [(0, 'thinking', 'thinking', 'considering'),
                                         (1, 'text', 'text', 'final answer')]:
            stream({'type': 'content_block_start', 'index': index,
                    'content_block': {'type': kind, field: ''}})
            stream({'type': 'content_block_delta', 'index': index,
                    'delta': {field: text}})
            self.runner._native_event(root, record, {'type': 'assistant', 'message': {
                'id': 'native-message', 'content': [{'type': kind, field: text}]}})
            stream({'type': 'content_block_stop', 'index': index})
        rows = [json.loads(line) for line in (root/'activity-events.jsonl').read_text().splitlines()]
        result = project([{'raw': row['event'], 'received_at': row['received_at']} for row in rows])
        self.assertEqual([lane['item']['type'] for lane in result['items']], ['reasoning', 'agentMessage'])
        self.assertEqual(result['items'][1]['item']['text'], 'final answer')
        self.assertFalse(any(lane.get('conflicting_receipts') for lane in result['items']))
        self.assertTrue(all(lane['ended'] for lane in result['items']))

    def test_restart_resumes_same_profile_session_and_snapshot(self):
        with self.invoke():
            first = self.runner.start(self.payload)
        runtime = self.runner.container
        restarted = ClaudeRunner(self.runner.state, self.runner.store.root, self.source, container=runtime)
        self.assertNotEqual(self.runner.instance_id, restarted.instance_id)
        with patch.object(restarted, '_check_auth', return_value='sha256:'+'a'*64), \
             patch.object(restarted, '_invoke', side_effect=lambda root, record, prompt, flag, **kw:
                          {'session_id': record['thread_id'], 'result': 'resumed'}):
            result = restarted.resume(first['run_id'], 'continue',
                expected_post_run_hash=first['post_run_hash'], expected_thread_id=first['thread_id'],
                model='sonnet', effort='low')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['thread_id'], first['thread_id'])
        self.assertEqual(result['profile'], first['profile'])
        self.assertEqual(len(result['turns']), 2)

    def test_partial_text_updates_are_visible_before_terminal_receipt(self):
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()), active_host_turn=str(uuid4()))
        root = self.runner._run_dir(record['run_id'])
        for value in [
            {'type': 'message_start', 'message': {'id': 'native-message'}},
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'visible now'}},
        ]:
            self.runner._native_event(root, record, {'type': 'stream_event', 'event': value})
        rows = [json.loads(line) for line in (root/'activity-events.jsonl').read_text().splitlines()]
        result = project([{'raw': row['event'], 'received_at': row['received_at']} for row in rows])
        self.assertEqual(result['items'][0]['item']['text'], 'visible now')
        self.assertIsNone(result['items'][0]['ended'])

    def test_tool_completion_retains_native_name_arguments_and_result(self):
        record = self.runner._prepare(self.payload)
        record.update(thread_id=str(uuid4()), active_host_turn=str(uuid4()))
        root = self.runner._run_dir(record['run_id'])
        for kind, block in [('assistant', {'type': 'tool_use', 'id': 'native-tool',
            'name': 'Read', 'input': {'file_path': '/draft/SKILL.md'}}),
            ('user', {'type': 'tool_result', 'tool_use_id': 'native-tool', 'content': 'read result'})]:
            self.runner._native_event(root, record, {'type': kind, 'message': {'content': [block]}})
        event = json.loads((root/'activity-events.jsonl').read_text().splitlines()[-1])['event']
        self.assertEqual(event['params']['item']['tool'], 'Read')
        self.assertEqual(event['params']['item']['arguments']['file_path'], '/draft/SKILL.md')
        self.assertEqual(event['params']['item']['output'], 'read result')

    def test_native_skill_cannot_widen_controller_permissions(self):
        for index, extra in enumerate(['context: fork\n', 'hooks: {}\n', 'allowed-tools: Bash\n',
                                        'model: opus\n', '"hooks": {}\n']):
            name = 'unsafe-'+str(index)
            skill = self.root/name
            skill.mkdir()
            (skill/'SKILL.md').write_text('---\nname: '+name+'\ndescription: internal control\n'+extra+'---\nBody\n')
            pin = self.runner.store.import_skill(name, skill)
            with patch.object(self.runner, '_invoke') as native:
                with self.assertRaisesRegex(RunnerError, 'claude_native_skill_policy_unsupported'):
                    self.runner.start({**self.payload, 'skill_ref': {'skill_id': name,
                        'revision_id': pin['revision_id'], 'tree_hash': pin['tree_hash']}})
                native.assert_not_called()

    def test_controller_never_exposes_credential_side_file_or_shell_tools(self):
        args = command(None, 'sonnet', 'low', str(uuid4()), skill_ids=('selected',))
        self.assertEqual(args[args.index('--tools')+1], 'Skill')
        self.assertNotIn('Read', args[args.index('--allowedTools')+1])
        denied = args[args.index('--disallowedTools')+1].split(',')
        for name in ('Read', 'Write', 'Glob', 'Grep', 'Edit', 'Bash', 'Agent', 'Task'):
            self.assertIn(name, denied)

    def test_bom_or_ambiguous_frontmatter_cannot_hide_permission_overrides(self):
        for index, prefix in enumerate(['\ufeff---\n', '--- \n']):
            name = 'ambiguous-'+str(index)
            source = self.root/name
            source.mkdir()
            (source/'SKILL.md').write_text(prefix+'name: '+name+'\ndescription: Internal control\nhooks: {}\n---\nBody\n', encoding='utf-8')
            pin = self.runner.store.import_skill(name, source)
            with patch.object(self.runner, '_invoke') as native:
                with self.assertRaisesRegex(RunnerError, 'claude_native_skill_policy_unsupported'):
                    self.runner.start({**self.payload, 'skill_ref': {'skill_id':name,
                        'revision_id':pin['revision_id'], 'tree_hash':pin['tree_hash']}})
                native.assert_not_called()

    def test_missing_or_stale_supervisor_refuses_startup(self):
        runtime = object.__new__(ClaudeContainer)
        runtime.lease_service = self.root/'supervisor'
        with self.assertRaisesRegex(RunnerError, 'lease_service_unavailable'):
            runtime.check_supervisor()
        runtime.lease_service.mkdir()
        (runtime.lease_service/'service.json').write_text(json.dumps({'pid':123,'instance':'test'}))
        (runtime.lease_service/'service.alive').write_text(str(time.time()))
        (runtime.lease_service/'service.alive.monotonic').write_text(str(time.monotonic()))
        runtime.check_supervisor()
        (runtime.lease_service/'service.alive.monotonic').write_text('nan')
        with self.assertRaisesRegex(RunnerError, 'lease_service_unavailable'):
            runtime.check_supervisor()

    def test_command_capability_listens_only_on_loopback(self):
        service = CommandService(self.runner.container, self.root, {}, threading.Event(), time.monotonic()+20)
        try:
            self.assertEqual(service.server.server_address[0], '127.0.0.1')
        finally:
            service.close()

    def test_cancel_ack_does_not_race_execution_cleanup(self):
        record = self.runner._prepare(self.payload)
        record['status'] = 'running'
        from laomedo.agents.runtime.utils import _json
        _json(self.runner._run_dir(record['run_id'])/'record.json', record)
        flag = self.runner.cancel_flags[record['run_id']] = threading.Event()
        with patch('laomedo.host.leases.utils.cleanup_exact', side_effect=AssertionError('execution owns cleanup')):
            result = self.runner.cancel(record['run_id'])
        self.assertTrue(flag.is_set())
        self.assertTrue(result['cancel_requested'])
        self.assertFalse(result['cancel_confirmed'])

    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker runtime; covered by docker-runtime-controls")
    def test_command_worker_has_neither_profile_nor_network(self):
        runtime = ClaudeContainer.__new__(ClaudeContainer)
        runtime.profile, runtime.image_id = 'laomedo-claude-internal', 'sha256:'+'a'*64
        spec = runtime.spec(['sh', '-c', 'pwd'], worker=True)
        self.assertEqual(spec.network_mode, 'none')
        self.assertEqual(spec.mounts, [])
        self.assertTrue(spec.read_only)
        self.assertEqual(spec.cap_drop, ['ALL'])
        self.assertEqual(spec.environment['HOME'].get_secret_value(), '/tmp')


    def test_optional_skills_and_claude_handoff_are_accepted(self):
        result = envelope(None, {'provider': 'claude', 'model': 'sonnet', 'effort': 'low'},
                          'Read selected input', skills=[])
        self.assertEqual(result['skill_refs'], [])
        self.assertEqual(result['target']['provider'], 'claude')

    def test_execution_deadline_is_explicit_and_validated_before_native_work(self):
        with patch.object(self.runner, '_invoke') as native:
            for value in [0, -1, True, 86401, '180']:
                with self.assertRaisesRegex(RunnerError, 'claude_turn_timeout_invalid'):
                    self.runner.start({**self.payload, 'run_timeout_seconds': value})
            native.assert_not_called()
        record = self.runner._prepare({**self.payload, 'run_timeout_seconds': 300})
        self.assertEqual(record['turn_timeout'], 300)

    def test_dispatch_reuses_native_selection_after_editor_cache_expires(self):
        snapshot = self.runner.model_catalog()
        self.runner._catalog_cached = (time.monotonic()-301, snapshot)
        with patch.object(self.runner, 'model_catalog', side_effect=AssertionError('no discovery in dispatch')):
            record = self.runner._prepare(self.payload)
        self.assertEqual(record['resolved_model'], 'claude-sonnet')

    def test_cold_dispatch_refuses_without_blocking_on_native_discovery(self):
        self.runner._catalog_cached = None
        with patch.object(self.runner, 'model_catalog', side_effect=AssertionError('no discovery in ACK')):
            with self.assertRaisesRegex(RunnerError, 'runner_model_catalog_unavailable_check_runner_connection'):
                self.runner._prepare(self.payload)


if __name__ == '__main__':
    unittest.main()
