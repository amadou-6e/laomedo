"""Export actual native components without saving or executing a flow."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import urllib.request

p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
p.add_argument('--base',default='http://127.0.0.1:7864'); p.add_argument('--fake',action='store_true'); args=p.parse_args()
root=Path(__file__).resolve().parents[2]; config=json.loads(args.config.read_text())
token=json.load(urllib.request.urlopen(args.base+'/api/v1/auto_login'))['access_token']
def api(path, body):
    req=urllib.request.Request(args.base+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response:
        raw=response.read();return json.loads(gzip.decompress(raw) if response.headers.get('Content-Encoding')=='gzip' else raw)
def definition(path):return api('/api/v1/custom_component',{'code':path.read_text(encoding='utf-8')})['data']
issue_code=(root/'components/laomedo/github_issue.py').read_text()
if args.fake:
    helper=(root/'examples/github-issue/graph-components/prepare.py').read_text().split('class IssueOperationTask')[0]
    helper=helper.replace("'http://host.docker.internal:8785' + path", "'http://host.docker.internal:8786/v1/github-issues/' + path")
    issue_code=issue_code.replace('from laomedo.github_issue_client import issue_request', helper+"\ndef issue_request(action, **body): return call(action, body)\n")
issue=api('/api/v1/custom_component',{'code':issue_code})['data']
agent=definition(root/'components/laomedo/codex_agent.py');skill=definition(root/'components/laomedo/skill.py');contract=definition(root/'components/laomedo/output_contract.py')
prepare=definition(root/'examples/github-issue/graph-components/prepare.py');modify=definition(root/'examples/github-issue/graph-components/modify.py');close=definition(root/'examples/github-issue/graph-components/close.py');stop=definition(root/'examples/github-issue/graph-components/stop.py')
def setvalue(definition,key,value):definition['template'][key]['value']=value
nodes=[]; edges=[]
def node(identity,kind,definition,x,y):
    nodes.append({'id':identity,'type':'genericNode','position':{'x':x,'y':y},'data':{'id':identity,'type':kind,'node':copy.deepcopy(definition)}})
def edge(source,kind,output,target,field,output_types=['JSON'],input_types=['Data','JSON']):
    sh={'dataType':kind,'id':source,'name':output,'output_types':output_types};target_field=next(n for n in nodes if n['id']==target)['data']['node']['template'][field];th={'fieldName':field,'id':target,'inputTypes':target_field['input_types'],'type':target_field['type']}
    edges.append({'id':source+'-'+output+'-'+target+'-'+field,'source':source,'target':target,'sourceHandle':json.dumps(sh,separators=(',',':')).replace(chr(34),chr(339)),'targetHandle':json.dumps(th,separators=(',',':')).replace(chr(34),chr(339)),'data':{'sourceHandle':sh,'targetHandle':th}})
for index,action in enumerate(('modify','close')):
    number=config['approved'][action]['number']; original=config['issues'][str(number)]
    setvalue(issue,'repository_url','https://github.com/'+config['repository']);setvalue(issue,'state','all');setvalue(issue,'labels',[])
    issue['template']['issue_choice'].update(value='#'+str(number)+' '+original['title'],options=['#'+str(number)+' '+original['title']])
    node('issue-'+action,'LaomedoGitHubIssue',issue,20,index*500)
node('prepare','IssueOperationTask',prepare,440,220)
setvalue(skill,'source','');setvalue(skill,'skill_id',config['skill']['skill_id']);setvalue(skill,'revision_id',config['skill']['revision_id'])
skill['template']['skill_id']['options']=[config['skill']['skill_id']];skill['template']['revision_id']['options']=[config['skill']['revision_id']];setvalue(skill,'discovery_status','Pinned campaign reference')
node('skill','LaomedoSkill',skill,440,800)
setvalue(agent,'runner_url','http://host.docker.internal:8784');setvalue(agent,'output_retries',0);setvalue(agent,'timeout_seconds',240);setvalue(agent,'operation','fresh')
node('agent','LaomedoCodexAgent',agent,870,260)
setvalue(contract,'requirements_json',json.dumps({'schema_version':1,'fields':[{'name':'task_outcome','type':'string','required':True,'checks':{'enum':['success','failure']}},{'name':'operations','type':'object','required':True,'checks':{'nonempty':True}}]}))
node('contract','LaomedoOutputContract',contract,1300,260)
node('modify','ApplyIssueProposal',modify,1730,100);node('close','CloseAfterIssueUpdate',close,2160,100)
for index,route in enumerate(('failure','rejection','recovery')):
    node('review-'+route,'ReviewIssueProposal',stop,1730,580+index*300)
    edge('contract','LaomedoOutputContract',route,'review-'+route,'outcome')
for action in ('modify','close'):edge('issue-'+action,'LaomedoGitHubIssue','issue','prepare',action+'_issue')
edge('prepare','IssueOperationTask','task','agent','task',['Message'],['Message'])
edge('skill','LaomedoSkill','skill','agent','skill_reference')
edge('agent','LaomedoCodexAgent','submission','contract','agent_submission')
edge('contract','LaomedoOutputContract','success','modify','accepted')
edge('modify','ApplyIssueProposal','receipt','close','update_receipt')
flow={'name':('Credential-free fixture - ' if args.fake else '')+'Issue operations - Codex graph demo',
    'description':'Run Close issue after confirmed update to execute the full chain once. Host-scoped targets, no push/PR. Four-turn campaign cap. Failure/rejection/recovery do not write.',
    'data':{'nodes':nodes,'edges':edges,'viewport':{'x':20,'y':20,'zoom':0.35}}}
args.output.write_text(json.dumps(flow,indent=2),encoding='utf-8');print(json.dumps({'exported':True,'nodes':len(nodes),'edges':len(edges),'executed':False}))
