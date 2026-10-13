"""Prepare only the specifically owner-approved two disposable fixture issues."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.host_token_connection import HostTokenConnection
from laomedo.local_runner import _private
p=argparse.ArgumentParser(); p.add_argument('--state',type=Path,required=True); args=p.parse_args()
root=_private(args.state); root.mkdir(exist_ok=True)
if (root/'config.json').exists(): raise ValueError('campaign_already_prepared_no_reset')
repo='ga84jog/laomedo-exp104-disposable-20261007'
provider=HostTokenConnection(connection_id='issue-graph-demo',generation=1,repository=repo,
    token_file=Path('C:/CodeWorkspace/agentviz/.env'),key='GH_LAOMEDO',forbidden_mount=Path(__file__).parent/'demo-workspace')
rest=GitHubRestTransport(repo,lambda *args:provider.token('issue-graph-demo',1))
issues={}
for action, title in [('modify','Graph operation demo: update target'),('close','Graph operation demo: close target')]:
    receipt=root/(action+'-fixture.json')
    if receipt.exists():
        record=json.loads(receipt.read_text())
        if record['status']!='confirmed':raise ValueError('fixture_creation_unknown_do_not_repeat')
        number=record['number']
    else:
        marker='<!-- laomedo-issue-graph-fixture:'+uuid4().hex+' -->'
        receipt.write_text(json.dumps({'status':'unknown','marker':marker}),encoding='utf-8')
        body='Disposable saved Langflow issue-operation demo approved by the owner. '+marker
        raw=rest(repo,'issue_create',{'title':title,'body':body,'marker':marker})
        number=raw['number']; receipt.write_text(json.dumps({'status':'confirmed','number':number,'url':raw['html_url'],'marker':marker}),encoding='utf-8')
    issues[action]=rest(repo,'issue_read',{'number':number})
revision='sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349'
config={'campaign_id':uuid4().hex,'repository':repo,'turn_cap':4,
    'issues':{str(issue['number']):issue for issue in issues.values()},
    'approved':{'modify':{'number':issues['modify']['number'],'changes':{
        'title':issues['modify']['title'],'body':issues['modify']['body']+'\n\n## Agent operation verified\n\nUpdated through the saved Langflow graph.\n',
        'labels':sorted(set(issues['modify']['labels']+['question']))}},'close':{'number':issues['close']['number']}},
    'registry':'C:/Users/amado/AppData/Local/Temp/laomedo-standing-demo-20261012/skill-store',
    'source':str(Path(__file__).resolve().parent/'demo-workspace'),
    'skill':{'skill_id':'live-report','revision_id':revision,'tree_hash':revision}}
(root/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
print(json.dumps({'prepared':True,'targets':{a:i['number'] for a,i in issues.items()},'turns_used':0,'turn_cap':4}))
