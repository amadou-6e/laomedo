"""Internal controls; never presented as real Claude integration evidence."""
from pathlib import Path
import unittest
import json
import io
import os
import tempfile
from unittest.mock import patch

import laomedo
laomedo.__path__.append(str(Path(__file__).resolve().parents[2] / 'components/laomedo'))
from laomedo.claude_agent import LaomedoClaudeAgent
from laomedo.agents.contracts.output import requirements


class ClaudeComponentTests(unittest.IsolatedAsyncioTestCase):
    def test_resume_payload_contains_visible_execution_timeout(self):
        prior={'provider':'claude','run_id':'11111111-1111-4111-8111-111111111111',
               'status':'completed','post_run_hash':'sha256:'+'a'*64,'thread_id':'native-thread',
               'model':'sonnet','effort':'low'}
        payload=self.node(operation='resume',run_reference=None,run_reference_json=json.dumps(prior),
                          run_timeout_seconds=321)._prepare()[1]
        self.assertEqual(payload['run_timeout_seconds'],321)

    async def test_dropdown_refresh_uses_provider_catalog_and_preserves_selection(self):
        node = self.node()
        with patch.object(node, '_model_catalog', return_value={'sonnet':['low','medium','high'],'opus':['low','medium','high']}) as catalog:
            config = await node.update_build_config({'model': {'value': 'sonnet'}, 'effort': {'value': 'low'}}, 'opus', 'model')
        self.assertEqual(config['model']['value'], 'opus')
        self.assertEqual(config['effort']['value'], 'low')
        self.assertEqual(config['model']['options'], ['sonnet','opus'])
        self.assertFalse(config['model']['combobox'])
        catalog.assert_called_once()

    def test_template_order_types_and_visibility_match_current_codex(self):
        base=LaomedoClaudeAgent.__bases__[0]
        expected=[item for item in base.inputs if item.name != 'handoff_reference']
        self.assertEqual([item.name for item in LaomedoClaudeAgent.inputs],[item.name for item in expected]+['run_timeout_seconds'])
        for actual,reference in zip(LaomedoClaudeAgent.inputs,expected):
            self.assertIs(type(actual),type(reference))
            self.assertEqual(actual.show,reference.show)
            self.assertEqual(actual.advanced,reference.advanced)
        fields={item.name:item for item in LaomedoClaudeAgent.inputs}
        self.assertEqual(fields['model'].options,[])
        self.assertEqual(fields['effort'].options,[])
        self.assertTrue(fields['model'].refresh_button)
        self.assertEqual(fields['runner_url'].value,'http://host.docker.internal:8769')
        self.assertTrue(fields['run_timeout_seconds'].advanced)
        self.assertNotIn('handoff_reference',fields)
        self.assertEqual(fields['run_timeout_seconds'].value,180)

    async def test_catalogue_failure_does_not_add_unrequested_inputs(self):
        node=self.node()
        config={'model':{'value':'sonnet'},'effort':{'value':'low'}}
        with patch.object(node,'_model_catalog',side_effect=RuntimeError('runner_model_catalog_unavailable_check_runner_connection')):
            with self.assertRaises(RuntimeError):
                await node.update_build_config(config,'sonnet','model')
        self.assertNotIn('handoff_reference',config)

    def test_model_refresh_uses_claude_runner_token_not_codex_token(self):
        import laomedo.codex_agent as codex
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'claude-token').write_text('claude-control');(root/'codex-token').write_text('codex-control')
            with patch.dict(os.environ,{'LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE':str(root/'claude-token'),
                                       'LAOMEDO_RUNNER_TOKEN_FILE':str(root/'codex-token')}), \
                 patch.object(codex._HTTP,'open',return_value=io.BytesIO(b'{"provider":"claude","models":[{"id":"sonnet","efforts":["low"]}]}')) as http:
                result=self.node()._model_catalog({'runner_url':{'value':'http://localhost:8769'}})
            self.assertEqual(result,{'sonnet':['low']})
            self.assertEqual(http.call_args.args[0].get_header('Authorization'),'Bearer claude-control')
            self.assertEqual(http.call_args.kwargs['timeout'],75)

    def test_resolved_model_efforts_follow_first_native_match_like_runner(self):
        import laomedo.codex_agent as codex
        body={'provider':'claude','models':[
            {'id':'default','resolved_model':'claude-opus-test','efforts':['low']},
            {'id':'opus','resolved_model':'claude-opus-test','efforts':['low','max']}]}
        with tempfile.TemporaryDirectory() as directory:
            token=Path(directory)/'token';token.write_text('internal-control')
            with patch.dict(os.environ,{'LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE':str(token)}), \
                 patch.object(codex._HTTP,'open',return_value=io.BytesIO(json.dumps(body).encode())):
                catalog=self.node()._model_catalog({'runner_url':{'value':'http://localhost:8769'}})
        self.assertEqual(catalog.effort_aliases['claude-opus-test'],['low'])
        self.assertEqual(catalog['opus'],['low','max'])

    async def test_native_labels_and_all_efforts_reach_dropdown_and_dispatch_payload(self):
        import laomedo.codex_agent as codex
        node=self.node(model='fable',effort='max')
        catalog=codex._ModelCatalog()
        catalog['fable']=['low','medium','high','xhigh','max']
        catalog.metadata['fable']={'id':'fable','display_name':'Fable test','resolved_model':'claude-fable-test'}
        with patch.object(node,'_model_catalog',return_value=catalog):
            config=await node.update_build_config({'model':{'value':'fable'},'effort':{'value':'max'}},'fable','model')
        self.assertEqual(config['model']['options_metadata'],[catalog.metadata['fable']])
        self.assertEqual(config['effort']['options'],catalog['fable'])
        self.assertEqual(node._prepare()[1]['effort'],'max')

    async def test_model_switch_replaces_unsupported_effort_with_explicit_default_choice(self):
        node=self.node()
        with patch.object(node,'_model_catalog',return_value={'old':['default']}):
            config=await node.update_build_config({'model':{'value':'sonnet'},'effort':{'value':'high'}},'old','model')
        self.assertEqual(config['effort']['options'],['default'])
        self.assertEqual(config['effort']['value'],'default')

    async def test_imported_resolved_model_keeps_native_efforts_and_pin_without_duplicate_picker_rows(self):
        import laomedo.codex_agent as codex
        node=self.node(model='claude-sonnet-test',effort='max')
        catalog=codex._ModelCatalog();catalog['sonnet']=['low','max']
        catalog.effort_aliases['claude-sonnet-test']=['low','max']
        catalog.metadata['claude-sonnet-test']={'id':'claude-sonnet-test','laomedo_native_model':True,
                                               'display_name':'Sonnet test','resolved_model':'claude-sonnet-test'}
        with patch.object(node,'_model_catalog',return_value=catalog):
            config=await node.update_build_config({'model':{'value':'claude-sonnet-test'},'effort':{'value':'max'}},'claude-sonnet-test','model')
        self.assertEqual(config['model']['value'],'claude-sonnet-test')
        self.assertEqual(config['model']['options'],['sonnet','claude-sonnet-test'])
        self.assertEqual(config['effort']['options'],['low','max'])
        self.assertEqual(config['effort']['value'],'max')

    def test_skills_are_optional_but_connected_references_are_validated(self):
        for value in (None, "", []):
            with self.subTest(value=value):
                payload=self.node(skill_reference=value)._prepare()[1]
                self.assertEqual(payload['skill_refs'],[])
                self.assertNotIn('skill_ref',payload)
        for value in ({}, [None], {'skill_id':'broken'}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'invalid_skill_reference'):
                self.node(skill_reference=value)._prepare()
        ref={'skill_id':'sample','revision_id':'sha256:'+'a'*64,'tree_hash':'sha256:'+'a'*64}
        with self.assertRaisesRegex(ValueError,'duplicate_skill_id'):
            self.node(skill_reference=[ref,ref])._prepare()
        with self.assertRaisesRegex(ValueError,'one_to_sixteen_skills_required'):
            self.node(skill_reference=[ref]*17)._prepare()

    def node(self, **changes):
        node = LaomedoClaudeAgent()
        for key, value in {'operation': 'fresh', 'task': 'Internal control', 'model': 'sonnet',
            'effort': 'low', 'runner_url': 'http://localhost:8769', 'timeout_seconds': 210,
            'skill_id': 'sample', 'revision_id': 'sha256:' + 'a' * 64, **changes}.items():
            setattr(node, key, value)
        node._pre_run_setup()
        if 'skill_reference' not in changes:
            node.skill_reference = {'skill_id': 'sample', 'revision_id': 'sha256:' + 'a' * 64,
                                    'tree_hash': 'sha256:' + 'a' * 64}
        return node

    async def test_outputs_share_one_dispatch_and_keep_claude_provider(self):
        import asyncio
        node = self.node()
        with patch.object(node, '_http', return_value={'provider': 'claude', 'run_id': 'internal',
                'status': 'completed', 'answer': 'answer'}) as dispatch:
            answer, reference = await asyncio.gather(node.answer_output(), node.run_output())
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(answer.text, 'answer')
        self.assertEqual(reference.data['provider'], 'claude')

    def test_runner_provider_mismatch_is_checked_by_subclass(self):
        base = LaomedoClaudeAgent.__bases__[0]
        with patch.object(base, '_http', return_value={'provider': 'codex'}):
            with self.assertRaisesRegex(RuntimeError, 'runner_provider_mismatch'):
                self.node()._http('http://localhost:8769', {}, 'POST')

    def test_static_contract_reaches_runner_and_foreign_provider_refuses(self):
        pin = requirements({'schema_version': 1, 'fields': []})
        prepared = self.node(output_requirements_json=json.dumps(pin), output_retries=1)._prepare()[1]
        self.assertEqual(prepared['output_requirements'], pin)
        self.assertEqual(prepared['output_retries'], 1)
        with self.assertRaisesRegex(ValueError, 'run_provider_mismatch'):
            self.node(operation='resume', run_reference={'provider': 'codex'})._prepare()

    def test_hidden_saved_feedback_pin_is_not_lost_from_runner_request(self):
        from types import SimpleNamespace
        pin = requirements({'schema_version': 1, 'fields': []})
        node = self.node(output_requirements_json='', output_retries=2)
        node._vertex = SimpleNamespace(id='agent', graph=SimpleNamespace(edges=[]),
            full_data={'data': {'node': {'template': {'output_requirements_json': {
                'show': False, 'value': json.dumps(pin)}}}}})
        payload = node._prepare()[1]
        self.assertEqual(payload['output_requirements'], pin)
        self.assertEqual(payload['output_retries'], 2)

    def test_predispatch_failure_preserves_public_code_and_redacts_unknown_payloads(self):
        from urllib.error import HTTPError
        import laomedo.codex_agent as common
        for code in ('claude_host_login_unavailable', 'claude_host_login_expired', 'claude_local_login_copy_failed', 'claude_model_required', 'claude_native_skill_policy_unsupported',
                     'unsupported_claude_effort', 'SECRET payload and token'):
            node = self.node(skill_reference=[])
            error = HTTPError('http://localhost:8769/v1/runs/async', 400, 'refused', {},
                              io.BytesIO(json.dumps({'error_category': code}).encode()))
            with patch.object(node, '_token', return_value='internal'), \
                 patch.object(common.request, 'urlopen', side_effect=error):
                expected = code if code != 'SECRET payload and token' else 'runner_dispatch_refused'
                with self.assertRaisesRegex(RuntimeError, '^'+expected+'$'):
                    node._http('http://localhost:8769/v1/runs/async', {}, 'POST')


if __name__ == '__main__':
    unittest.main()
