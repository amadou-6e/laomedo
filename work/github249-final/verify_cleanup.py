"""Independent live readback, safe preview restoration and grant cleanup."""
import json,os,sqlite3,subprocess
from pathlib import Path
from urllib.request import Request,urlopen
from uuid import uuid4
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.host.mediation.store import MediationStore
from laomedo.github.interface.pull_requests.client import pr_request


def main():
 root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);targets=json.loads((state/'live-targets.json').read_text());repo=targets['repository'];connection=HostTokenConnection(connection_id='github249-readback',generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO')
 def get(path):
  request=Request('https://api.github.com/repos/'+repo+path,headers={'Authorization':'Bearer '+connection.token('github249-readback',1),'Accept':'application/vnd.github+json','User-Agent':'Laomedo-authorized-readback'})
  with urlopen(request,timeout=30) as response:return json.load(response)
 issue=get('/issues/'+str(targets['issue']['number']));pr=get('/pulls/'+str(targets['pr']['number']));assert issue['title']=='GitHub Issue refactor verified' and issue['state']=='closed';assert {v['name'] for v in issue['labels']}=={'bug','documentation'};assert pr['title']=='GitHub PR response recovery verified'
 subprocess.run([__import__('sys').executable,str(Path(__file__).with_name('authorize.py')),'pr'],check=True,capture_output=True)
 os.environ['LAOMEDO_GITHUB_PR_URL']='http://127.0.0.1:18794';os.environ['LAOMEDO_GITHUB_PR_TOKEN_FILE']=str(state/'pr-api-token')
 restored=pr_request('execute',repository_url='https://github.com/'+repo,labels=[],state='open',pr_number=targets['pr']['number'],operation={'action':'modify','request_id':str(uuid4()),'grant_ref':targets['pr']['grant_ref'],'changes':{'title':'Original Codex Agent feedback verified'}});assert restored['operation']['status']=='succeeded'
 pr=get('/pulls/'+str(targets['pr']['number']));assert pr['title']=='Original Codex Agent feedback verified';assert pr['head']['sha']==targets['pr']['sha'] and pr['head']['ref']==targets['pr']['branch'] and pr['base']['ref']==targets['pr']['base'];assert pr['state']=='open' and pr['draft'] is True;assert pr['body']=='Disposable target for real Laomedo PR249 validation. Created by the trusted host under the user-approved disposable repository scope.'
 scopes={};records={}
 for kind in ['issue','pr']:
  store=MediationStore(state/(kind+'.db'))
  with sqlite3.connect(state/(kind+'.db')) as db:
   runs=[r[0] for r in db.execute('SELECT run_id FROM grants WHERE approval_identity=?',('user-authorized-disposable-validation-pr249',))]
   records[kind]=[{'run_id':r[0],'effect_id':r[1],'state':r[2]} for r in db.execute('SELECT run_id,effect_id,state FROM effects')]
  scopes[kind]=sum(store.revoke_run(run) for run in runs);(state/(kind+'-bindings.json')).write_text('{}',encoding='utf-8')
  with sqlite3.connect(state/(kind+'.db')) as db:assert db.execute('SELECT count(*) FROM grants WHERE approval_identity=? AND revoked_at IS NULL',('user-authorized-disposable-validation-pr249',)).fetchone()[0]==0
 native=json.loads((e/'live-agent-result.json').read_text());record=json.loads((state/'runner/runs'/native['runner_run_id']/'record.json').read_text());containers=subprocess.check_output(['docker','ps','-aq','--filter','label=laomedo.run_id='+native['runner_run_id']],text=True).strip();assert not containers,'Owned native container remains'
 result={'head':'3786201298fe729ddf3d315c2d70e4b079a8c36b','issue':{'number':issue['number'],'title':issue['title'],'state':issue['state'],'labels':sorted(v['name'] for v in issue['labels'])},'pr':{'number':pr['number'],'title':pr['title'],'state':pr['state'],'draft':pr['draft'],'head_base_and_body_preserved':True},'effects':records,'revoked_grants':scopes,'all_campaign_grants_revoked':True,'native_run':{'run_id':record['run_id'],'thread_id':record.get('thread_id'),'status':record['status'],'owned_container_absent':True},'restoration':'Ordinary scoped host operation restored the Agent example title after the separate response-loss checks; no additional model call.','readback':'Independent direct GitHub GET, separate from node viewer and mutation acknowledgement.'}
 (e/'live-readback-cleanup.json').write_bytes(json.dumps(result,indent=2).encode());print(json.dumps(result))

if __name__=='__main__':main()
