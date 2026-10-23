"""Internal controls; never presented as real Claude integration evidence."""
from pathlib import Path
import unittest
import json
from unittest.mock import patch

import laomedo
laomedo.__path__.append(str(Path(__file__).resolve().parents[2] / 'components/laomedo'))
from laomedo.claude_agent import LaomedoClaudeAgent
from laomedo.output_contract import requirements


class ClaudeComponentTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_selection_refresh_does_not_use_codex_catalog(self):
        node = self.node()
        with patch.object(node, '_model_catalog', side_effect=AssertionError('Codex catalog must not be called')):
            config = await node.update_build_config({'model': {'value': 'sonnet'}, 'effort': {'value': 'low'}}, 'opus', 'model')
        self.assertEqual(config['model']['value'], 'opus')
        self.assertEqual(config['effort']['value'], 'low')

    def node(self, **changes):
        node = LaomedoClaudeAgent()
        for key, value in {'operation': 'fresh', 'task': 'Internal control', 'model': 'sonnet',
            'effort': 'low', 'runner_url': 'http://localhost:8769', 'timeout_seconds': 210,
            'skill_id': 'sample', 'revision_id': 'sha256:' + 'a' * 64, **changes}.items():
            setattr(node, key, value)
        node._pre_run_setup()
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
