"""Execute the real two-node feedback graph, including negative controls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lfx.graph.graph.base import Graph
from lfx.schema import Message
from lfx.custom.custom_component.component import Component
from laomedo.github_pr_gateway import GitHubPRGateway
from laomedo.github_mediation import MediationStore
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.pr_agent_loop import operation_value
import test_live_github_pr as fixtures

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pr_loop_builder',ROOT/'examples/github-pr/build_flow.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


class PRAgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ,{'LANGFLOW_CONFIG_DIR':self.temp.name,
            'LANGFLOW_DATABASE_URL':'sqlite:///'+(Path(self.temp.name)/'lf.db').as_posix()})
        self.env.start(); self.addCleanup(self.env.stop)
        self.fake = fixtures.FakeGitHub()
        self.store = MediationStore(Path(self.temp.name)/'mediation.db')
        _, token = self.store.issue(run_id='fixture-run',invocation_id='fixture-invoke',repository='owner/repo',
            operations={'pr_node_update'},branch='demo',target_prs={1:'main'},ttl_seconds=60)
        self.gateway = GitHubPRGateway({'owner/repo':GitHubRestTransport('owner/repo',lambda:'DUMMY',opener=self.fake)},
            self.store,lambda ref:{'token':token,'run_id':'fixture-run','repository':'owner/repo'} if ref=='fixture-grant' else None)
        self.operations = 0
        self.agent_calls = []
        original_update = Component.update_ctx
        def observe(component, values):
            if type(component).__name__ == 'PRFixtureAgent' and 'pr_fixture_agent_calls' in values:
                self.agent_calls.append(values['pr_fixture_agent_task'])
            return original_update(component, values)
        observer = patch.object(Component,'update_ctx',new=observe)
        observer.start(); self.addCleanup(observer.stop)
        self.before_apply = None
        def request(action,**body):
            if body.get('operation'):
                self.operations += 1
                if self.before_apply: self.before_apply()
            return self.gateway.discover(**body) if action=='discover' else self.gateway.execute(**body)
        self.client = patch('laomedo.github_pr_client.pr_request',side_effect=request)
        self.client.start(); self.addCleanup(self.client.stop)

    async def execute(self, action='modify', flow=None):
        graph = Graph.from_payload(flow or builder.build(action))
        result = await asyncio.wait_for(graph.arun(inputs=[{}],outputs=['pr']),timeout=25)
        self.last_graph = graph
        return str(result)

    async def test_modify_uses_exact_return_port_and_agent_runs_once(self):
        result = await self.execute()
        self.assertIn('succeeded',result)
        self.assertEqual(len(self.agent_calls),1)
        self.assertIn('https://github.com/owner/repo/pull/1',self.agent_calls[0])
        self.assertEqual(len(self.fake.writes),1)
        self.assertEqual(self.fake.prs[1]['title'],'PR operation verified')
        self.assertEqual(len(self.last_graph.vertices),2)

    async def test_close_applies_once_and_stops(self):
        self.assertIn('succeeded',await self.execute('close'))
        self.assertEqual(self.fake.prs[1]['state'],'closed')
        self.assertEqual(len(self.agent_calls),1)

    async def test_repeated_graph_run_does_not_repeat_mutation(self):
        await self.execute(); self.assertIn('succeeded',await self.execute())
        self.assertEqual(len(self.fake.writes),1)
        self.assertEqual(len(self.agent_calls),2)

    async def test_failed_initial_read_does_not_run_agent(self):
        flow = builder.build(); flow['data']['nodes'][0]['data']['node']['template']['pr_choice']['value']=''
        self.assertIn('selected_pr_required',await self.execute(flow=flow))
        self.assertEqual(len(self.agent_calls),0)
        self.assertEqual(self.operations,0)

    async def test_invalid_agent_response_cannot_write(self):
        self.assertIn('pr_operation_invalid',await self.execute('invalid'))
        self.assertEqual(self.operations,0)
        self.assertEqual(len(self.fake.writes),0)

    async def test_agent_failure_cannot_write_or_retry(self):
        self.assertIn('pr_agent_failed',await self.execute('fail'))
        self.assertEqual(len(self.agent_calls),1)
        self.assertEqual(self.operations,0)

    async def test_changed_pr_during_agent_is_refused(self):
        self.before_apply = lambda: self.fake.prs[1].update(body='Concurrent user edit')
        self.assertIn('pr_changed_since_agent_read',await self.execute())
        self.assertEqual(self.fake.prs[1]['body'],'Concurrent user edit')
        self.assertEqual(len(self.fake.writes),0)

    async def test_unknown_write_stops_without_agent_or_write_retry(self):
        self.fake.timeout_after_write = True
        self.assertIn('unknown',await self.execute())
        self.assertEqual(len(self.agent_calls),1)
        self.assertEqual(len(self.fake.writes),1)
        self.assertEqual(self.operations,1)

    async def test_inline_operation_and_loop_are_refused_without_effect(self):
        flow = builder.build()
        flow['data']['nodes'][0]['data']['node']['template']['operation']['value']={
            'action':'close','request_id':'inline','grant_ref':'fixture-grant'}
        self.assertIn('pr_agent_loop_invalid',await self.execute(flow=flow))
        self.assertEqual(self.operations,0)
        self.assertEqual(len(self.fake.writes),0)

    async def test_cancelled_agent_cannot_dispatch_a_write(self):
        started = asyncio.Event()
        async def pending_agent(component, seed):
            started.set()
            await asyncio.Future()
        with patch('laomedo.pr_agent_loop.agent_operation',new=pending_agent):
            run = asyncio.create_task(self.execute())
            await asyncio.wait_for(started.wait(),timeout=10)
            run.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await run
        self.assertEqual(self.operations,0)
        self.assertEqual(len(self.fake.writes),0)

    def test_message_feedback_json_is_supported_but_invalid_or_oversized_refused(self):
        operation={'action':'close','request_id':'once','grant_ref':'fixture-grant'}
        self.assertEqual(operation_value(Message(text=json.dumps(operation))),operation)
        for value in ('not-json','x'*(1024*1024+1),{'action':'merge'},None):
            with self.assertRaisesRegex(ValueError,'pr_operation_invalid'): operation_value(value)
