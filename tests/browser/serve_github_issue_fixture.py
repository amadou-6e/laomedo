import argparse,json,sys,tempfile,secrets
parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=str,required=True);args=parser.parse_args()
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from test_live_github_issue import FakeGitHub
from laomedo.github_issue_gateway import GitHubIssueGateway
from laomedo.github_issue_server import server
from laomedo.github_mediation import MediationStore
from laomedo.github_rest_transport import GitHubRestTransport
root=Path(tempfile.mkdtemp(prefix='laomedo-live-issue-fixture-'))
store=MediationStore(root/'mediation.sqlite',now=lambda:100.0,monotonic=lambda:0.0)
_,cap=store.issue(run_id='fixture-run',invocation_id='fixture-invoke',repository='owner/repo',operations={'issue_update'},target_issues={1},ttl_seconds=60)
fake=FakeGitHub();transport=GitHubRestTransport('owner/repo',lambda:'DUMMY-PROVIDER-TOKEN',opener=fake)
gateway=GitHubIssueGateway({'owner/repo':transport},store,lambda ref: {'token':cap,'run_id':'fixture-run','repository':'owner/repo'} if ref=='fixture' else None)
api_token=secrets.token_urlsafe(40);(root/'token').write_text(api_token,encoding='utf-8')
service=server(gateway,api_token,port=0)
manifest={'root':str(root),'port':service.server_address[1],'token_file':str(root/'token'),'provider':'fake-no-network','model_turns':0}
Path(args.manifest).write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('credential-free GitHub fixture ready',flush=True);service.serve_forever()
