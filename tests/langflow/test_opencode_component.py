"""Run in pinned Langflow with components/ prepended to PYTHONPATH."""

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
# Test the installed runtime and component sources together without shadowing
# the runtime's shared evaluator with the component file of the same name.
import laomedo
laomedo.__path__.append(str(ROOT / "components/laomedo"))
from laomedo.opencode_agent import LaomedoOpenCodeAgent
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


class OpenCodeComponentTests(unittest.IsolatedAsyncioTestCase):
    def node(self, **changes):
        node = LaomedoOpenCodeAgent()
        for key, value in {"operation": "fresh", "task": "Read fixture", "model": "test/model",
            "effort": "default", "runner_url": "http://localhost:8767", "timeout_seconds": 210,
            "skill_reference": [{"skill_id": "sample", "revision_id": "sha256:" + "a" * 64,
                                  "tree_hash": "sha256:" + "a" * 64}],
            "skill_id": "", "revision_id": "", "run_reference": None, **changes}.items():
            setattr(node, key, value)
        node._pre_run_setup()
        return node

    async def test_current_controls_and_provider_model_refresh(self):
        node=self.node()
        fields={item.name:item.model_dump() for item in node.inputs}
        self.assertEqual(fields['model']['options'],[])
        self.assertFalse(fields['model']['combobox'])
        self.assertEqual(fields['effort']['options'],['default'])
        for name in ('run_reference','run_reference_json','skill_id','revision_id','request_id'):
            self.assertFalse(fields[name]['show'])
        order=[item.name for item in node.inputs]
        self.assertLess(order.index('model'),order.index('skill_reference'))
        with patch.object(LaomedoOpenCodeAgent,'_model_catalog',return_value={'test/model':['default'],'test/other':['default']}):
            await node.update_build_config(fields,'test/other','model')
        self.assertEqual(fields['model']['value'],'test/other')
        self.assertEqual(fields['model']['options'],['test/model','test/other'])
        self.assertEqual(fields['effort']['options'],['default'])

    async def test_model_refresh_uses_only_opencode_runner_credential(self):
        import json
        import os
        import tempfile
        import laomedo.agents.interface.langflow.component as codex
        node = self.node()
        fields = {item.name: item.model_dump() for item in node.inputs}
        fields["runner_url"]["value"] = node.runner_url
        with tempfile.TemporaryDirectory() as directory:
            opencode_token = Path(directory) / "opencode"
            codex_token = Path(directory) / "codex"
            opencode_token.write_text("opencode-test-only", encoding="utf-8")
            codex_token.write_text("codex-test-only", encoding="utf-8")
            with patch.dict(os.environ, {"LAOMEDO_OPENCODE_RUNNER_TOKEN_FILE": str(opencode_token),
                                         "LAOMEDO_RUNNER_TOKEN_FILE": str(codex_token)}), \
                    patch.object(codex._HTTP, "open") as opened:
                opened.return_value.__enter__.return_value.read.return_value = json.dumps({
                    "models": [{"id": "test/model", "efforts": ["default"]}]}).encode()
                await node.update_build_config(fields, "test/model", "model")
            self.assertEqual(opened.call_count, 1)
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, "http://localhost:8767/v1/models")
            self.assertEqual(request.get_header("Authorization"), "Bearer opencode-test-only")
            self.assertEqual(fields["model"]["options"], ["test/model"])

    async def test_blank_port_uses_saved_json_reference_and_checks_provider(self):
        import json
        from uuid import uuid4
        prior={'provider':'opencode','status':'completed','run_id':str(uuid4()),'thread_id':'session',
               'post_run_hash':'sha256:'+'a'*64,'model':'test/model','effort':'default'}
        node=self.node(operation='resume',run_reference='',run_reference_json=json.dumps(prior))
        endpoint,payload,method=node._prepare()
        self.assertTrue(endpoint.endswith('/'+prior['run_id']+'/resume'))
        self.assertEqual(payload['expected_thread_id'],'session')
        with self.assertRaisesRegex(ValueError,'run_provider_mismatch'):
            self.node(operation='resume',run_reference='',run_reference_json=json.dumps({**prior,'provider':'codex'}))._prepare()

    async def test_saved_hidden_reference_survives_actual_graph_execution(self):
        import json
        from uuid import uuid4
        from lfx.graph.graph.base import Graph
        from lfx.services.manager import get_service_manager
        from lfx.services.schema import ServiceType
        from lfx.services.settings.service import SettingsService
        manager=get_service_manager()
        if ServiceType.SETTINGS_SERVICE not in manager.services:
            manager.services[ServiceType.SETTINGS_SERVICE]=SettingsService.initialize()
        flow=json.loads((ROOT/'examples/opencode-node/flow.json').read_text())
        agent=next(n for n in flow['data']['nodes'] if n['id']=='OpenCode-read-project')
        template,_=build_custom_component_template(Component(_code=(ROOT/'components/laomedo/opencode_agent.py').read_text()))
        agent['data']['node']=template
        fields=template['template'];run_id=str(uuid4())
        fields['operation']['value']='status';fields['run_reference']['value']=''
        fields['run_reference_json']['value']=json.dumps({'provider':'opencode','run_id':run_id})
        flow['data']['nodes']=[agent];flow['data']['edges']=[]
        from laomedo.integrations.langflow.agent.component import AgentComponent
        with patch.object(AgentComponent,'_http',return_value={'provider':'opencode','run_id':run_id,'status':'completed','answer':'Recorded result'}) as http:
            await Graph.from_payload(flow).arun(inputs=[{'input_value':''}],types=['chat'])
        self.assertEqual(http.call_count,1)
        endpoint,body,method=http.call_args.args
        self.assertEqual(method,'GET')
        self.assertTrue(endpoint.endswith('/'+run_id))

    async def test_graph_upgrade_does_not_launch_model_discovery(self):
        new={'display_name':'OpenCode','template':{'code':{'type':'code','value':'new'},
            'model':{'type':'str','value':''},'effort':{'type':'str','value':'default'}}}
        from copy import deepcopy
        old=deepcopy(new);old['template']['model'].update(value='test/model',options=['test/model','test/other'])
        with patch.object(LaomedoOpenCodeAgent,'_model_catalog',side_effect=AssertionError('Implicit discovery')):
            updated=await self.node().update_frontend_node(new,old)
        self.assertEqual(updated['template']['model']['value'],'test/model')
        self.assertEqual(updated['template']['model']['options'],['test/model','test/other'])

    async def test_both_outputs_share_one_dispatch(self):
        node = self.node()
        value = {"provider": "opencode", "run_id": "fixture", "status": "completed", "answer": "answer"}
        with patch.object(LaomedoOpenCodeAgent, "_http", return_value=value) as dispatch:
            outputs = await asyncio.gather(node.answer_output(), node.run_output())
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(outputs[0].text, "answer")

    async def test_unsupported_variant_and_foreign_resume_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_opencode_effort"):
            self.node(effort="high")._prepare()
        with self.assertRaisesRegex(ValueError, "run_provider_mismatch"):
            self.node(operation="resume", run_reference={"provider": "codex"})._prepare()

    async def test_template_ports_and_multiple_skills(self):
        code = (ROOT / "components/laomedo/opencode_agent.py").read_text()
        template, _ = build_custom_component_template(Component(_code=code))
        self.assertTrue(template["template"]["skill_reference"]["list"])
        self.assertEqual([item["types"] for item in template["outputs"]], [["Message"], ["JSON"], ["JSON"]])
        refs = self.node().skill_reference
        refs.append({**refs[0], "skill_id": "second"})
        self.assertEqual(len(self.node(skill_reference=refs)._prepare()[1]["skill_refs"]), 2)


if __name__ == "__main__":
    unittest.main()
