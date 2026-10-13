"""Export actual native components without saving or executing a flow."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import urllib.request
from graph_prompt import prompt_template

p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
p.add_argument('--base',default='http://127.0.0.1:7864'); p.add_argument('--fake',action='store_true'); args=p.parse_args()
root=Path(__file__).resolve().parents[2]; config=json.loads(args.config.read_text())
token=json.load(urllib.request.urlopen(args.base+'/api/v1/auto_login'))['access_token']
def api(path, body):
    req=urllib.request.Request(args.base+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response:
        raw=response.read();return json.loads(gzip.decompress(raw) if response.headers.get('Content-Encoding')=='gzip' else raw)
def definition(path):
    code=path.read_text(encoding='utf-8')
    if args.fake:code=code.replace('host.docker.internal:8785','host.docker.internal:8795')
    return api('/api/v1/custom_component',{'code':code})['data']
issue_code=(root/'components/laomedo/github_issue.py').read_text()
client=(root/'laomedo/github_issue_client.py').read_text()
client=client.replace('from .skill_source_client import NoRedirect', 'class NoRedirect(request.HTTPRedirectHandler):\n    def redirect_request(self, *_): return None')
client=client.replace('from .github_issue_contract import', 'from laomedo.github_issue_contract import')
client=client.replace('base = os.environ.get("LAOMEDO_GITHUB_ISSUE_URL", "")', 'base = "http://host.docker.internal:8785"')
# The native Issue class is unchanged; only its existing backend transport is bound to this demo service.
if args.fake:client=client.replace('host.docker.internal:8785','host.docker.internal:8795')
operation_issue_code=issue_code.replace('from laomedo.github_issue_client import issue_request',client)
operation_issue=api('/api/v1/custom_component',{'code':operation_issue_code})['data']
issue=operation_issue if args.fake else api('/api/v1/custom_component',{'code':issue_code})['data']
agent=definition(root/'components/laomedo/codex_agent.py');skill=definition(root/'components/laomedo/skill.py');contract=definition(root/'components/laomedo/output_contract.py')
operations=definition(root/'examples/github-issue/graph-components/operations.py');close=definition(root/'examples/github-issue/graph-components/confirmed_close.py');stop=definition(root/'examples/github-issue/graph-components/stop.py')
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
with urllib.request.urlopen(urllib.request.Request(args.base+'/api/v1/all',headers={'Authorization':'Bearer '+token}),timeout=60) as response:
    raw=response.read();catalog=json.loads(gzip.decompress(raw) if response.headers.get('Content-Encoding')=='gzip' else raw)
prompt=copy.deepcopy(next(value for group in catalog.values() if isinstance(group,dict) for value in group.values() if isinstance(value,dict) and value.get('display_name')=='Prompt Template'))
prompt['template']['template']['value']=prompt_template(config)
prompt['custom_fields']={'template':['update_issue','close_issue']}
for variable in ('update_issue','close_issue'):
    prompt['template'][variable]={'name':variable,'display_name':variable,'type':'str','input_types':['Message'],'value':'','show':True,'multiline':True,'required':False,'list':False,'advanced':False,'dynamic':False}
node('prompt','Prompt Template',prompt,440,220)
setvalue(skill,'source','');setvalue(skill,'skill_id',config['skill']['skill_id']);setvalue(skill,'revision_id',config['skill']['revision_id'])
skill['template']['skill_id']['options']=[config['skill']['skill_id']];skill['template']['revision_id']['options']=[config['skill']['revision_id']];setvalue(skill,'discovery_status','Pinned campaign reference')
node('skill','LaomedoSkill',skill,440,800)
setvalue(agent,'runner_url','http://host.docker.internal:'+('8794' if args.fake else '8784'));setvalue(agent,'output_retries',0);setvalue(agent,'timeout_seconds',240);setvalue(agent,'operation','fresh')
node('agent','LaomedoCodexAgent',agent,870,260)
setvalue(contract,'requirements_json',json.dumps({'schema_version':1,'fields':[{'name':'task_outcome','type':'string','required':True,'checks':{'enum':['success','failure']}},{'name':'operations','type':'object','required':True,'checks':{'nonempty':True}}]}))
node('contract','LaomedoOutputContract',contract,1300,260)
node('operations','IssueOperationData',operations,1730,100)
node('confirmed','ConfirmedUpdateRoute',close,2600,100)
for index,action in enumerate(('modify','close')):
    number=config['approved'][action]['number'];original=config['issues'][str(number)]
    setvalue(operation_issue,'repository_url','https://github.com/'+config['repository']);setvalue(operation_issue,'state','all');setvalue(operation_issue,'labels',[])
    operation_issue['template']['issue_choice'].update(value='#'+str(number)+' '+original['title'],options=['#'+str(number)+' '+original['title']])
    node('apply-'+action,'LaomedoGitHubIssue',operation_issue,2160+index*870,100)
for index,route in enumerate(('failure','rejection','recovery')):
    node('review-'+route,'ReviewIssueProposal',stop,1730,580+index*300)
    edge('contract','LaomedoOutputContract',route,'review-'+route,'outcome')
for action,variable in [('modify','update_issue'),('close','close_issue')]:edge('issue-'+action,'LaomedoGitHubIssue','task','prompt',variable,['Message'],['Message'])
edge('prompt','Prompt Template','prompt','agent','task',['Message'],['Message'])
edge('skill','LaomedoSkill','skill','agent','skill_reference')
edge('agent','LaomedoCodexAgent','submission','contract','agent_submission')
edge('contract','LaomedoOutputContract','success','operations','accepted')
edge('operations','IssueOperationData','modify','apply-modify','operation')
edge('issue-modify','LaomedoGitHubIssue','issue','apply-modify','issue_reference')
edge('apply-modify','LaomedoGitHubIssue','operation_result','confirmed','update_result')
edge('operations','IssueOperationData','operations','confirmed','operations')
edge('confirmed','ConfirmedUpdateRoute','operation','apply-close','operation')
edge('issue-close','LaomedoGitHubIssue','issue','apply-close','issue_reference')
flow={'name':('Credential-free fixture - ' if args.fake else '')+'Issue Operation inputs - Codex graph demo',
    'description':'Run the final GitHub Issue (close target) to execute the full chain once. Host-scoped targets, no push/PR. Campaign cap: '+str(config.get('turn_cap',4))+' turns. Failure/rejection/recovery do not write.',
    'data':{'nodes':nodes,'edges':edges,'viewport':{'x':20,'y':20,'zoom':0.35}}}
args.output.write_text(json.dumps(flow,indent=2),encoding='utf-8');print(json.dumps({'exported':True,'nodes':len(nodes),'edges':len(edges),'executed':False}))
