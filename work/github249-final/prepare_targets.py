"""Host-authorized disposable targets and short-lived exact-target grants."""
import json,secrets
from pathlib import Path
from urllib.request import Request,urlopen
from uuid import uuid4
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.host.mediation.store import MediationStore


def main():
 root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);repo='ga84jog/laomedo-exp104-disposable-20261007'
 connection=HostTokenConnection(connection_id='github249-setup',generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO')
 def request(method,path,body=None):
  data=None if body is None else json.dumps(body).encode()
  r=Request('https://api.github.com/repos/'+repo+path,data=data,method=method,headers={'Authorization':'Bearer '+connection.token('github249-setup',1),'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json','User-Agent':'Laomedo-authorized-validation'})
  with urlopen(r,timeout=45) as response:return json.load(response)
 old=request('GET','/pulls/24');branch='refactor-249-validation-'+secrets.token_hex(4)
 request('POST','/git/refs',{'ref':'refs/heads/'+branch,'sha':old['head']['sha']})
 pr=request('POST','/pulls',{'head':branch,'base':old['base']['ref'],'title':'GitHub refactor validation pending','body':'Disposable target for real Laomedo PR249 validation. Created by the trusted host under the user-approved disposable repository scope.','draft':True})
 (state/'created-pr.json').write_bytes(json.dumps({'number':pr['number'],'branch':branch,'base':pr['base']['ref'],'sha':pr['head']['sha'],'url':pr['html_url']}).encode())
 issue=request('POST','/issues',{'title':'GitHub refactor validation issue','body':'Disposable target for actual Issue node modify/close and recovery validation for Laomedo PR249. No production issue is affected.'})
 target={'repository':repo,'pr':{'number':pr['number'],'title':pr['title'],'branch':branch,'base':pr['base']['ref'],'sha':pr['head']['sha'],'url':pr['html_url']},'issue':{'number':issue['number'],'title':issue['title'],'url':issue['html_url']},'authorization':'Existing explicit user authorization: create any PR/issues needed in this disposable repository; continuation selected GitHub PR249.'}
 for kind,operations in [('issue',{'issue_update'}),('pr',{'pr_node_update'})]:
  current=HostTokenConnection(connection_id='github249-'+kind,generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO')
  store=MediationStore(state/(kind+'.db'),connection_is_current=current.current);run=str(uuid4());ref='github249-'+kind+'-'+secrets.token_hex(8)
  grant_id,token=store.issue(run_id=run,invocation_id=str(uuid4()),repository=repo,operations=operations,ttl_seconds=1800,branch=branch if kind=='pr' else None,target_prs={pr['number']:pr['base']['ref']} if kind=='pr' else None,target_issues={issue['number']} if kind=='issue' else None,connection_id='github249-'+kind,connection_generation=1,approval_identity='user-authorized-disposable-validation-pr249')
  (state/(kind+'-bindings.json')).write_bytes(json.dumps({ref:{'token':token,'run_id':run,'repository':repo}}).encode())
  target[kind]['grant_ref']=ref;target[kind]['run_id']=run;target[kind]['grant_id']=grant_id
  if kind=='pr':(state/'feedback-bindings.json').write_bytes(json.dumps({repo+'#'+str(pr['number']):ref}).encode())
 (state/'live-targets.json').write_bytes(json.dumps(target,indent=2).encode());safe={k:v for k,v in target.items()};(e/'live-targets.json').write_bytes(json.dumps(safe,indent=2).encode());print(json.dumps({'created_pr':pr['number'],'created_issue':issue['number'],'authority':'host-issued, exact-target, 30minute grants; no credentials in graph'}))

if __name__=='__main__':main()
