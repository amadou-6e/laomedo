import base64, hashlib, json, sqlite3, subprocess, sys
from pathlib import Path
from experiments.exp139.prepare import connection, CONNECTION, REPOSITORY, BRANCH
from laomedo.github_rest_transport import GitHubRestTransport

from laomedo.siwc_auth import _outside_git
root=_outside_git(Path(sys.argv[1]))
config=json.loads((root/'config.json').read_bytes())
provider=connection(root,Path(config['token_file']))
rest=GitHubRestTransport(REPOSITORY,provider.token)
with sqlite3.connect('file:'+ (root/'host/mediator/mediator.sqlite').as_posix()+'?mode=ro',uri=True) as db:
    rows=db.execute("SELECT run_id,state,result_json FROM effects WHERE operation='pr_create'").fetchall()
assert len(rows)==1 and rows[0][1]=='confirmed','no_confirmed_pr_receipt'
run_id=rows[0][0]
receipt=json.loads(rows[0][2]); number=receipt['number']
assert type(number)==int and number>0
pr=rest._call('GET',f'/repos/{REPOSITORY}/pulls/{number}',None,CONNECTION,1)
assert pr['draft'] is True and pr['head']['repo']['full_name']==REPOSITORY and pr['head']['ref']==BRANCH and pr['base']['ref']==config['base']
commit=pr['head']['sha']; assert len(commit)==40 and all(c in '0123456789abcdef' for c in commit)
from urllib import request
file_request=request.Request(f'https://api.github.com/repos/{REPOSITORY}/pulls/{number}/files?per_page=100',
 headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+provider.token(CONNECTION,1),
          'X-GitHub-Api-Version':'2026-03-10','User-Agent':'laomedo-exp139-readback'},method='GET')
with rest.opener.open(file_request,timeout=15) as response:
 raw_files=response.read(1024*1024+1)
 assert len(raw_files)<=1024*1024 and not response.headers.get('Link'), 'file_list_incomplete'
 files=json.loads(raw_files)
assert isinstance(files,list) and all(isinstance(item,dict) for item in files)
report_path='experiments/exp139/issue-report.md'
assert len(files)==1 and files[0]['filename']==report_path and files[0]['status']=='added'
content=rest._call('GET',f'/repos/{REPOSITORY}/contents/{report_path}?ref={commit}',None,CONNECTION,1)
assert content['encoding']=='base64' and content['size']<65536
data=base64.b64decode(content['content'])
assert hashlib.sha256(data).hexdigest()==config['report_sha256']
inputs=json.loads((root/'flow-input/inputs.json').read_bytes()); frozen=inputs['snapshot']; issue=frozen['context']['issue']
body_digest=hashlib.sha256(issue['body'].encode()).hexdigest()
assert issue['url'].encode() in data and body_digest.encode() in data and frozen['snapshot_id'].encode() in data
secrets=[provider.token(CONNECTION,1),(root/'runner/api-token').read_text().strip()]
auth=subprocess.run(['docker','run','--rm','--pull=never','--network','none','--user','10001:10001',
 '--mount','type=volume,source=laomedo-122-docker-auth,target=/profile,readonly',
 '--entrypoint','cat','sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78','/profile/auth.json'],capture_output=True,timeout=30)
assert auth.returncode==0
def tokens(v):
    if isinstance(v,dict):
        for k,item in v.items():
            if k in {'access_token','refresh_token','id_token','OPENAI_API_KEY'} and isinstance(item,str) and item: secrets.append(item)
            else: tokens(item)
    elif isinstance(v,list):
        for item in v: tokens(item)
tokens(json.loads(auth.stdout))
for value in [data,json.dumps(pr).encode(),json.dumps(files).encode()]:
    assert not any(secret.encode() in value for secret in secrets),'published_credential_match'
result={'run_id':run_id,'number':number,'url':f'https://github.com/{REPOSITORY}/pull/{number}',
 'draft':True,'head_commit':commit,'base_branch':config['base'],'head_branch':BRANCH,
 'only_expected_report_changed':True,'published_report_sha256':hashlib.sha256(data).hexdigest(),
 'frozen_issue_snapshot':frozen['snapshot_id'],'frozen_issue_body_sha256':body_digest,
 'report_contains_frozen_issue_identity':True,'published_current_credential_matches':False,
 'credential_scan_limit':'Current stored login values only; historical rotated values not covered.',
 'provider_writes_by_this_readback':0}
(root/'readback.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,sort_keys=True))
