import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from laomedo.github_mediation import MediationStore
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.output_contract import requirements
from test_live_github_issue import FakeGitHub

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('issue_graph_demo', ROOT/'examples/github-issue/graph_demo.py')
demo = importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)

class IssueGraphDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.fake = FakeGitHub(); self.rest = GitHubRestTransport('owner/repo', lambda *args, **kwargs: 'DUMMY', opener=self.fake)
        self.config = {'repository':'owner/repo', 'campaign_id':'graph-demo',
            'issues':{str(n):self.rest('owner/repo', 'issue_read', {'number':n}) for n in (1,2)},
            'approved':{'modify':{'number':1, 'changes':{'title':'Approved title', 'body':'Approved body', 'labels':['research']}}, 'close':{'number':2}},
            'skill': {'skill_id':'fixture', 'revision_id':'sha256:'+'a'*64, 'tree_hash':'sha256:'+'a'*64}}
        self.record = {'run_id':'native', 'status':'completed', 'evidence_complete':True,
            'completion_basis':'native_trace_closure', 'snapshot_ready':True,
            'requirements_revision':requirements(demo.FORM)['requirements_revision'],
            'answer':json.dumps({'task_outcome':'success', 'operations':self.config['approved']})}
        owner = self
        class Engine:
            def status(self, run_id):
                if run_id != 'native': raise ValueError('unknown run')
                return owner.record
        self.store = MediationStore(self.root/'issues.sqlite', connection_is_current=lambda *_: True)
        self.controller = demo.DemoController(self.root, self.config, Engine(), self.rest, self.store)
    def test_exact_preparation_has_no_effect_or_grant(self):
        self.assertEqual(self.controller.prepare_task({'modify':self.config['issues']['1'],'close':self.config['issues']['2']})['task'], demo.task(self.config))
        self.assertFalse((self.root/'binding.json').exists()); self.assertEqual(self.fake.patch_count,0)
    def test_native_record_is_fetched_and_false_success_refused(self):
        for key, value in [('status','unknown'), ('completion_basis','process_exit'), ('evidence_complete',False), ('snapshot_ready',False), ('requirements_revision','sha256:'+'0'*64)]:
            original=self.record[key]; self.record[key]=value
            with self.assertRaises(ValueError): self.controller.apply('modify','native')
            self.record[key]=original
        self.assertEqual(self.fake.patch_count,0)
    def test_update_then_close_revokes_and_replay_does_not_write(self):
        first=self.controller.apply('modify','native'); self.assertEqual(first['result']['operation']['status'],'succeeded')
        self.assertEqual(self.controller.apply('close','native')['result']['operation']['status'],'succeeded')
        self.assertEqual(self.fake.patch_count,2)
        self.assertEqual(self.controller.apply('close','native')['result']['operation']['status'],'succeeded')
        self.assertEqual(self.fake.patch_count,2)
        with self.assertRaises(ValueError): self.controller.prepare_task({'modify':self.config['issues']['1'],'close':self.config['issues']['2']})
    def test_close_cannot_jump_over_update(self):
        with self.assertRaisesRegex(ValueError,'update_not_confirmed'): self.controller.apply('close','native')
        self.assertEqual(self.fake.patch_count,0)
    def test_unknown_update_stops_close_and_replay(self):
        self.fake.timeout_after_write=True
        result=self.controller.apply('modify','native'); self.assertEqual(result['result']['operation']['status'],'unknown')
        with self.assertRaisesRegex(ValueError,'update_not_confirmed'): self.controller.apply('close','native')
        self.controller.apply('modify','native'); self.assertEqual(self.fake.patch_count,1)
        self.assertEqual(self.fake.issues[2]['state'],'open')
    def test_source_changed_refuses_before_grant(self):
        self.fake.issues[2]['body']='changed'
        with self.assertRaisesRegex(ValueError,'issue_changed'): self.controller.apply('modify','native')
        self.assertEqual(self.fake.patch_count,0); self.assertFalse((self.root/'binding.json').exists())
    def test_wrong_approved_plan_refuses(self):
        self.record['answer']=json.dumps({'task_outcome':'success','operations':{}})
        with self.assertRaisesRegex(ValueError,'agent_plan_not_exactly_approved'):self.controller.apply('modify','native')
        self.assertEqual(self.fake.patch_count,0)
    def test_authorization_returns_operation_data_without_writing(self):
        bundle=self.controller.authorized_operations('native')['operations']
        self.assertEqual(self.fake.patch_count,0)
        self.assertEqual(set(bundle['modify']),{'action','changes','request_id','grant_ref'})
        self.assertEqual(bundle['modify']['changes'],self.config['approved']['modify']['changes'])
        self.assertNotIn(self.controller.binding['token'],json.dumps(bundle))
        result=self.controller.execute_issue('https://github.com/owner/repo',[],'all',1,bundle['modify'])
        self.assertEqual(result['operation']['status'],'succeeded')
        result=self.controller.execute_issue('https://github.com/owner/repo',[],'all',2,bundle['close'])
        self.assertEqual(result['operation']['status'],'succeeded')
        self.assertEqual(self.fake.patch_count,2)
    def test_forged_close_result_and_modified_operation_cannot_write(self):
        bundle=self.controller.authorized_operations('native')['operations']
        with self.assertRaisesRegex(ValueError,'update_not_confirmed'):
            self.controller.execute_issue('https://github.com/owner/repo',[],'all',2,bundle['close'])
        for payload,number in [({**bundle['modify'],'changes':{'title':'not approved'}},1),(bundle['modify'],3)]:
            with self.assertRaisesRegex(ValueError,'issue_operation_conflict'):
                self.controller.execute_issue('https://github.com/owner/repo',[],'all',number,payload)
        self.assertEqual(self.fake.patch_count,0)
    def test_export_handles_use_native_type_and_roundtrip(self):
        tree=ast.parse((ROOT/'examples/github-issue/build_graph_demo.py').read_text())
        function=next(item for item in tree.body if isinstance(item,ast.FunctionDef) and item.name=='edge')
        namespace={'json':json,'nodes':[{'id':'agent','data':{'node':{'template':{'task':{'type':'str','input_types':['Message']}}}}}], 'edges':[]}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<edge>','exec'),namespace)
        namespace['edge']('prepare','IssueOperationTask','task','agent','task',['Message'],['Message'])
        edge=namespace['edges'][0]
        self.assertEqual(edge['data']['targetHandle']['type'],'str')
        for side in ('source','target'):
            handle=edge[side+'Handle']
            self.assertIn(chr(339),handle)
            self.assertEqual(json.loads(handle.replace(chr(339),chr(34))),edge['data'][side+'Handle'])
    def test_runner_refuses_unbounded_request_and_resume(self):
        engine=object.__new__(demo.BoundedRunner); engine.bind(self.config,self.root)
        body={'request_id':'fixture', 'task':demo.task(self.config), 'model':'gpt-6-luna','effort':'low','skill_ref':self.config['skill'], 'output_requirements':requirements(demo.FORM),'output_retries':0}
        with patch.object(demo.LocalRunner,'start_async', return_value={'status':'running'}) as dispatch:
            engine.start_async(body); self.assertEqual(dispatch.call_count,1)
            for key,value in [('task','unapproved'),('model','other'),('output_retries',1)]:
                with self.assertRaises(ValueError):engine.start_async({**body,key:value})
            self.assertEqual(dispatch.call_count,1)
        with self.assertRaises(ValueError):engine.resume('native','retry')
if __name__=='__main__':unittest.main()
