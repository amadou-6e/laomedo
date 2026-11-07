"""Recover the exact disposable targets after refused overlong grant setup."""
import json
from pathlib import Path
from urllib.request import Request,urlopen
from laomedo.host.credentials.token.connection import HostTokenConnection


def main():
 root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);repo='ga84jog/laomedo-exp104-disposable-20261007'
 connection=HostTokenConnection(connection_id='github249-setup',generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO')
 def get(path):
  r=Request('https://api.github.com/repos/'+repo+path,headers={'Authorization':'Bearer '+connection.token('github249-setup',1),'Accept':'application/vnd.github+json','User-Agent':'Laomedo-authorized-validation'})
  with urlopen(r,timeout=45) as response:return json.load(response)
 saved=json.loads((state/'created-pr.json').read_text());pr=get('/pulls/'+str(saved['number']));issues=get('/issues?state=all&per_page=100')
 selected=[i for i in issues if i.get('title')=='GitHub refactor validation issue' and i.get('created_at','')>=pr['created_at'] and i.get('body')=='Disposable target for actual Issue node modify/close and recovery validation for Laomedo PR249. No production issue is affected.']
 assert len(selected)==1,'Ambiguous issue setup; do not create or select another target'
 issue=selected[0];target={'repository':repo,'pr':{'number':pr['number'],'title':pr['title'],'branch':pr['head']['ref'],'base':pr['base']['ref'],'sha':pr['head']['sha'],'url':pr['html_url'],'grant_ref':'github249-pr-live'},'issue':{'number':issue['number'],'title':issue['title'],'url':issue['html_url'],'grant_ref':'github249-issue-live'},'authorization':'User-authorized disposable repository; setup created only these targets. Grant requests must use actual production maximum60seconds, immediately before bounded operations.'}
 for path in [state/'live-targets.json',e/'live-targets.json']:path.write_bytes(json.dumps(target,indent=2).encode())
 (state/'feedback-bindings.json').write_bytes(json.dumps({repo+'#'+str(pr['number']):target['pr']['grant_ref']}).encode())
 for kind in ['issue','pr']:(state/(kind+'-bindings.json')).write_text('{}',encoding='utf-8')
 print(json.dumps({'pr':pr['number'],'issue':issue['number'],'setup':'Recovered exact existing targets; no repeated create','grants':'None; maximum60seconds will be respected'}))

if __name__=='__main__':main()
