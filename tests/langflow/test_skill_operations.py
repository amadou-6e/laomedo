"""Internal native-graph controls; fake Agent dispatch is not acceptance evidence."""
import asyncio
import importlib.util
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from lfx.graph.graph.base import Graph
from lfx.schema import Data
import test_skill_operations as controls

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('skill_ops_graph_builder', ROOT/'examples/skill-operations/build_flow.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class NativeSkillOperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.control = controls.SkillOperationTests()
        self.control.setUp()
        self.addCleanup(self.control.doCleanups)
        self.calls = 0
        self.agent_calls = 0
        def service(action, **body):
            self.calls += 1
            return getattr(self.control.service, action)(**body)
        self.client = patch('laomedo.skill_operation_client.skill_request', side_effect=service)
        self.client.start()
        self.addCleanup(self.client.stop)

    def build(self):
        return builder.build('internal-test', self.control.initial['revision_id'], 'sha256:'+'1'*64,
                             'http://127.0.0.1:8765', 'Change two files')

    async def test_feedback_runs_once_and_emits_traceable_reference(self):
        import json
        from lfx.custom.custom_component.component import Component
        flow = self.build()
        # Internal test-only component. Never export as the real working graph.
        code = '''from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message, Data
class LaomedoCodexAgent(Component):
    display_name = "Internal scheduler control"
    name = "LaomedoCodexAgent"
    inputs = [MessageTextInput(name="task", display_name="Task")]
    outputs = [Output(name="answer", display_name="Answer", method="answer_output")]
    def answer_output(self) -> Message:
        self._last_reference = {"status":"completed","run_id":"internal-run"}
        self.update_ctx({"internal_skill_agent_calls":1})
        return Message(text=PAYLOAD)
    def run_output(self) -> Data:
        return Data(data={})
    def submission_output(self) -> Data:
        return Data(data={})
'''.replace('PAYLOAD', repr(json.dumps(self.control.operation)))
        flow['data']['nodes'][1]['data']['node']['template']['code']['value'] = code
        original = Component.update_ctx
        def observe(component, values):
            if 'internal_skill_agent_calls' in values: self.agent_calls += 1
            return original(component, values)
        with patch.object(Component, 'update_ctx', observe):
            graph = Graph.from_payload(flow)
            result = await asyncio.wait_for(graph.arun(inputs=[{}], outputs=['skill']), timeout=30)
        self.assertIn('proposed', str(result))
        self.assertEqual(self.agent_calls, 1)
        self.assertEqual(self.calls, 2)

    async def test_external_agent_input_refused_before_operation(self):
        flow = self.build()
        extra = builder.builder.node(ROOT/'components/laomedo/skill.py', 'extra', {}, 900, 0)
        flow['data']['nodes'].append(extra)
        flow['data']['edges'].append(builder.builder.helper.edge(extra, 'skill', flow['data']['nodes'][1], 'skill_reference'))
        with self.assertRaisesRegex(Exception, 'pr_agent_loop_invalid'):
            graph = Graph.from_payload(flow)
            await asyncio.wait_for(graph.arun(inputs=[{}], outputs=['skill']), timeout=20)
        self.assertEqual(self.calls, 0)

    async def test_ordinary_operation_remains_acyclic(self):
        flow = self.normal_flow()
        graph = Graph.from_payload(flow)
        result = await asyncio.wait_for(graph.arun(inputs=[{}], outputs=['skill']), timeout=20)
        self.assertIn('proposed', str(result))
        self.assertEqual(self.calls, 2)
        self.assertEqual(self.agent_calls, 0)

    async def test_lost_apply_reply_is_unknown_without_second_commit(self):
        flow = self.normal_flow()
        def lost_reply(action, **body):
            value = getattr(self.control.service, action)(**body)
            if action == 'apply': raise OSError('internal lost response control')
            return value
        with patch('laomedo.skill_operation_client.skill_request', side_effect=lost_reply):
            result = await asyncio.wait_for(Graph.from_payload(flow).arun(inputs=[{}], outputs=['skill']), timeout=20)
        self.assertIn('unknown', str(result))
        self.assertEqual(len(self.control.service.history('internal-test', self.control.initial['revision_id'])['commits']), 2)

    def normal_flow(self):
        path = self.control.root/'internal_operation.py'
        path.write_text('''from lfx.custom.custom_component.component import Component
from lfx.io import Output
from lfx.schema import Data
class InternalSkillOperation(Component):
    display_name = "Internal operation control"
    name = "InternalSkillOperation"
    inputs = []
    outputs = [Output(name="operation", display_name="Operation", method="operation_output")]
    def operation_output(self) -> Data:
        return Data(data=PAYLOAD)
'''.replace('PAYLOAD', repr(self.control.operation)))
        flow = self.build()
        skill = flow['data']['nodes'][0]
        operation = builder.builder.node(path, 'operation', {}, 600, 0)
        flow['data']['nodes'] = [operation, skill]
        flow['data']['edges'] = [builder.builder.helper.edge(operation, 'operation', skill, 'operation')]
        return flow
