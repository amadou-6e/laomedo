"""Attach observational audit hooks to real GitHub services, with a PR response-loss relay."""
import json,os,subprocess
from pathlib import Path


def main():
 root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);source=root/'.tools/github-restored-245';work=root/'.tools/continuous-exp/work/github249-final';python='C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe';records=[]
 for kind,module,port in [('issue','issues','18793'),('pr','pull_requests','18804')]:
  env=os.environ.copy();env['PYTHONPATH']=str(source/'src');env['VALIDATION_HTTP_AUDIT_FILE']=str(state/(kind+'-github-http.jsonl'))
  args=[python,str(work/'serve_audited.py'),'laomedo.github.interface.'+module+'.cli','--repository','ga84jog/laomedo-exp104-disposable-20261007','--github-token-file',str(root/'.env'),'--github-token-key','GH_LAOMEDO','--connection-id','github249-'+kind,'--connection-generation','1','--api-token-file',str(state/(kind+'-api-token')),'--mediation-store',str(state/(kind+'.db')),'--grant-bindings',str(state/(kind+'-bindings.json')),'--port',port]
  if kind=='pr':args+=['--feedback-bindings',str(state/'feedback-bindings.json')]
  with (state/(kind+'-audited.log')).open('wb') as output:process=subprocess.Popen(args,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,cwd=source)
  records.append({'name':kind,'pid':process.pid,'port':int(port)})
 with (state/'pr-relay.log').open('wb') as output:process=subprocess.Popen([python,str(work/'relay.py'),'--port','18794','--upstream','18804','--audit',str(state/'pr-relay.jsonl'),'--drop-flag',str(state/'drop-next-pr-response')],stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,cwd=work)
 records.append({'name':'pr-relay','pid':process.pid,'port':18794});(state/'audited-processes.json').write_bytes(json.dumps(records).encode());print(json.dumps(records))

if __name__=='__main__':main()
