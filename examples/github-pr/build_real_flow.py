"""Export the two-node graph with a real installed Codex CLI agent."""
import argparse
import importlib.util
import json
from pathlib import Path
from uuid import uuid4
from lfx.graph.graph.base import Graph
from lfx.services.deps import get_settings_service

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('pr_builder',Path(__file__).with_name('build_flow.py'))
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

def build(repository,number,title,instructions,grant_ref,request_id):
    get_settings_service()
    node,edge=builder.builder.node,builder.builder.helper.edge
    pr=node(ROOT/'components/laomedo/github_pr.py','pr',{
        'repository_url':'https://github.com/'+repository,'pr_choice':f'#{number} {title}',
        'labels':[],'state':'open'},0,0)
    agent=node(ROOT/'components/laomedo/native_pr_agent.py','agent',{
        'instructions':instructions,'grant_ref':grant_ref,'request_id':request_id},600,120)
    source={'dataType':'NativePRAgent','id':'agent','name':'operation','output_types':['Data']}
    target={'id':'pr','fieldName':'operation','inputTypes':['Data','Message'],'type':'other'}
    feedback={'id':'agent-operation-pr-task','source':'agent','target':'pr',
        'sourceHandle':json.dumps(source),'targetHandle':json.dumps(target),
        'data':{'sourceHandle':source,'targetHandle':target}}
    flow={'name':'PR to Codex Agent to same PR','description':'Real Codex CLI and live GitHub. A scoped host grant is required to apply the proposed operation.',
        'flow_type':'workflow','access_type':'PRIVATE','data':{'nodes':[pr,agent],
        'edges':[edge(pr,'task',agent,'task'),feedback],'viewport':{'x':80,'y':40,'zoom':0.8}}}
    Graph.from_payload(flow)
    return flow

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for field in ('repository','title','instructions','grant-ref','output'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--number',type=int,required=True)
    parser.add_argument('--request-id',default=str(uuid4()))
    args=parser.parse_args()
    flow=build(args.repository,args.number,args.title,args.instructions,args.grant_ref,args.request_id)
    Path(args.output).write_text(json.dumps(flow,indent=2)+'\n',encoding='utf-8')
