"""A fresh real PR close target, exact grant, and independent closed-state verification."""
import importlib.util,json,os,secrets,sys
from pathlib import Path
from urllib.request import Request,urlopen
from uuid import uuid4
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.host.mediation.store import MediationStore


def main():
 root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);repo='ga84jog/laomedo-exp104-disposable-20261007';mode=sys.argv[1];connection=HostTokenConnection(connection_id='github249-close-setup',generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO')
 def request(method,path,body=None):
  r=Request('https://api.github.com/repos/'+repo+path,data=json.dumps(body).encode() if body else None,method=method,headers={'Authorization':'Bearer '+connection.token('github249-close-setup',1),'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'Laomedo-authorized-validation'})
  with urlopen(r,timeout=30) as response:return json.load(response)
 if mode=='setup':
  if (state/'close-target.json').exists():
   target=json.loads((state/'close-target.json').read_text());pr=request('GET','/pulls/'+str(target['number']));assert pr['state']=='open','Existing close target already terminal; do not repeat'
  else:
   previous=request('GET','/pulls/25');branch='refactor-249-close-'+secrets.token_hex(4);request('POST','/git/refs',{'ref':'refs/heads/'+branch,'sha':previous['head']['sha']});pr=request('POST','/pulls',{'head':branch,'base':previous['base']['ref'],'title':'Disposable PR close validation','body':'Temporary real target for Laomedo PR249 close-operation validation. The example Agent PR25 is kept open.','draft':True});target={'repository':repo,'number':pr['number'],'url':pr['html_url'],'branch':branch,'base':pr['base']['ref'],'sha':pr['head']['sha'],'grant_ref':'github249-pr-close','request_id':str(uuid4())};(state/'close-target.json').write_bytes(json.dumps(target).encode())
  flow=json.loads((state/'pr-ordinary-flow.json').read_text());flow['id']=str(uuid4());flow['name']='GitHub PR close operation';resource=next(n for n in flow['data']['nodes'] if n['id']=='pr');choice='#'+str(pr['number'])+' '+pr['title'];resource['data']['node']['template']['pr_choice'].update(value=choice,options=[choice]);operation={'action':'close','request_id':target['request_id'],'grant_ref':target['grant_ref']};next(n for n in flow['data']['nodes'] if n['id']=='operation')['data']['node']['template']['json_string']['value']=json.dumps(operation);(state/'close-flow.json').write_bytes(json.dumps(flow).encode());print(json.dumps({'created_or_reconciled_pr':pr['number']}));return

 target=json.loads((state/'close-target.json').read_text());store=MediationStore(state/'pr.db',connection_is_current=HostTokenConnection(connection_id='github249-pr',generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO').current)
 if mode=='authorize':
  run=str(uuid4());grant,token=store.issue(run_id=run,invocation_id=str(uuid4()),repository=repo,operations={'pr_node_update'},ttl_seconds=60,branch=target['branch'],target_prs={target['number']:target['base']},connection_id='github249-pr',connection_generation=1,approval_identity='user-authorized-disposable-validation-pr249');target['run_id']=run;(state/'close-target.json').write_bytes(json.dumps(target).encode());(state/'pr-bindings.json').write_bytes(json.dumps({target['grant_ref']:{'token':token,'run_id':run,'repository':repo}}).encode());return
 if mode=='verify':
  pr=request('GET','/pulls/'+str(target['number']));assert pr['state']=='closed' and pr['head']['sha']==target['sha'] and pr['base']['ref']==target['base'];effect=store.effect(target['run_id'],target['request_id']);assert effect['state']=='confirmed';revoked=store.revoke_run(target['run_id']);(state/'pr-bindings.json').write_text('{}',encoding='utf-8');result={'head':'9d8c65790d6722cd222907d17dddb3f20748f758','pr':pr['number'],'state':'closed','host_effect':'confirmed','head_base_preserved':True,'grant_revoked':revoked==1,'independent_readback':True};(e/'live-pr-close.json').write_bytes(json.dumps(result,indent=2).encode());print(json.dumps(result));return
 raise ValueError('unknown_mode')

if __name__=='__main__':main()
