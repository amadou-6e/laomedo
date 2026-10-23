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
from laomedo.output_contract import requirements


class ClaudeComponentTests(unittest.IsolatedAsyncioTestCase):
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
        expected=[item for item in base.inputs if item.name not in {'bridge_url','handoff_reference'}]
        self.assertEqual([item.name for item in LaomedoClaudeAgent.inputs],[item.name for item in expected])
        for actual,reference in zip(LaomedoClaudeAgent.inputs,expected):
            self.assertIs(type(actual),type(reference))
            self.assertEqual(actual.show,reference.show)
            self.assertEqual(actual.advanced,reference.advanced)
        fields={item.name:item for item in LaomedoClaudeAgent.inputs}
        self.assertEqual(fields['model'].options,['sonnet','opus','haiku'])
        self.assertEqual(fields['effort'].options,['low','medium','high'])
        self.assertTrue(fields['model'].refresh_button)
        self.assertEqual(fields['runner_url'].value,'http://host.docker.internal:8769')

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


if __name__ == '__main__':
    unittest.main()
