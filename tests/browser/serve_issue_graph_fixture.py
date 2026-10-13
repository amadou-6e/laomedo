"""Fake model and fake GitHub only; native Langflow nodes still execute."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from uuid import uuid4
from laomedo.github_issue_server import server
from laomedo.github_mediation import MediationStore
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.local_runner import serve
from laomedo.output_contract import requirements
root=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(root/'tests'));sys.path.insert(0,str(root/'examples/github-issue'))
from test_live_github_issue import FakeGitHub
spec=importlib.util.spec_from_file_location('graph_demo',root/'examples/github-issue/graph_demo.py');demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--token-file',type=Path,required=True);args=p.parse_args()
state=Path(tempfile.mkdtemp(prefix='laomedo-issue-graph-fake-'));fake=FakeGitHub()
rest=GitHubRestTransport('owner/repo',lambda *args:'DUMMY',opener=fake)
config={'repository':'owner/repo','campaign_id':'fake-graph','issues':{str(n):rest('owner/repo','issue_read',{'number':n}) for n in (1,2)},
 'approved':{'modify':{'number':1,'changes':{'title':'Graph fixture updated','body':'Approved fixture update','labels':['research']}},'close':{'number':2}},
 'skill':{'skill_id':'live-report','revision_id':'sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349','tree_hash':'sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349'}}
(state/'config.json').write_text(json.dumps(config),encoding='utf-8')
class Engine:
    api_token=args.token_file.read_text().strip()
    record=None
    def start_async(self,body,**kwargs):
        if body['task']!=demo.task(config) or body.get('output_requirements')!=requirements(demo.FORM):raise ValueError('fixture_request_mismatch')
        self.record={'request_id':body['request_id'],'client_request_id':body['request_id'],'request_hash':'sha256:'+hashlib.sha256(json.dumps({k:v for k,v in body.items() if k!='request_id'},sort_keys=True,separators=(',',':')).encode()).hexdigest(),'run_id':str(uuid4()),'thread_id':'fake-thread','status':'completed','attempt_finished':True,
          'answer':json.dumps({'task_outcome':'success','operations':config['approved']}),'evidence_complete':True,
          'completion_basis':'native_trace_closure','snapshot_ready':True,'post_run_hash':'sha256:'+'a'*64,
          'requirements_revision':requirements(demo.FORM)['requirements_revision'],'precheck':{'installed':True,'call_count':1},'error_category':None}
        return self.record
    def status(self,run_id):
        if self.record is None or self.record['run_id']!=run_id:raise ValueError('unknown_run')
        return self.record
    def lookup_request(self,request_id):return self.record
engine=Engine();store=MediationStore(state/'issues.sqlite',connection_is_current=lambda *_:True)
controller=demo.DemoController(state,config,engine,rest,store)
services=[serve(engine,port=8794),demo.service(controller,engine.api_token,8795),server(controller.gateway,engine.api_token,8796)]
for srv in services:threading.Thread(target=srv.serve_forever,daemon=True).start()
args.manifest.write_text(json.dumps({'provider':'fake-no-network','state':str(state),'config':str(state/'config.json'),'model_turns':0}),encoding='utf-8')
print('Fake issue graph fixture ready',flush=True)
try:
    while True:time.sleep(1)
finally:
    for srv in services:srv.shutdown()
