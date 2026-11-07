"""Issue an exact,60-second host grant immediately before its live operation."""
import json,sys
from pathlib import Path
from uuid import uuid4
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.host.mediation.store import MediationStore


def main():
 kind=sys.argv[1];assert kind in {'issue','pr'};root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);targets=json.loads((state/'live-targets.json').read_text());repo=targets['repository'];target=targets[kind]
 connection=HostTokenConnection(connection_id='github249-'+kind,generation=1,repository=repo,token_file=root/'.env',key='GH_LAOMEDO');store=MediationStore(state/(kind+'.db'),connection_is_current=connection.current);run=str(uuid4());grant,token=store.issue(run_id=run,invocation_id=str(uuid4()),repository=repo,operations={'pr_node_update' if kind=='pr' else 'issue_update'},ttl_seconds=60,branch=target.get('branch'),target_prs={target['number']:target['base']} if kind=='pr' else None,target_issues={target['number']} if kind=='issue' else None,connection_id='github249-'+kind,connection_generation=1,approval_identity='user-authorized-disposable-validation-pr249')
 (state/(kind+'-bindings.json')).write_bytes(json.dumps({target['grant_ref']:{'token':token,'run_id':run,'repository':repo}}).encode());(state/(kind+'-live-authorization.json')).write_bytes(json.dumps({'grant_id':grant,'run_id':run,'target':target['number'],'ttl_seconds':60}).encode());print(json.dumps({'target':target['number'],'ttl_seconds':60,'run_id':run}))

if __name__=='__main__':main()
