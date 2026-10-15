"""Export the PR round trip using the existing Laomedo Codex Agent/runner."""
import argparse
import importlib.util
import json
from pathlib import Path
from lfx.graph.graph.base import Graph
from lfx.services.deps import get_settings_service

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('pr_builder',Path(__file__).with_name('build_flow.py'))
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

def build(repository,number,title,skill_id,revision_id,runner_url='http://127.0.0.1:8765'):
    get_settings_service()
    node,edge=builder.builder.node,builder.builder.helper.edge
    pr=node(ROOT/'components/laomedo/github_pr.py','pr',{
        'repository_url':'https://github.com/'+repository,'pr_choice':f'#{number} {title}',
        'labels':[],'state':'open'},0,0)
    agent=node(ROOT/'components/laomedo/codex_agent.py','agent',{
        'operation':'fresh','skill_id':skill_id,'revision_id':revision_id,
        'runner_url':runner_url},600,120)
    flow={'name':'PR to existing Codex Agent to same PR',
        'description':'Requires a real runner, a pinned operation skill and a scoped GitHub connection. Original-runner acceptance remains unverified.',
        'flow_type':'workflow','access_type':'PRIVATE','data':{'nodes':[pr,agent],
        'edges':[edge(pr,'task',agent,'task'),edge(agent,'answer',pr,'operation')],
        'viewport':{'x':80,'y':40,'zoom':0.8}}}
    Graph.from_payload(flow)
    return flow

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for field in ('repository','title','skill-id','revision-id','output'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--number',type=int,required=True)
    parser.add_argument('--runner-url',default='http://127.0.0.1:8765')
    args=parser.parse_args()
    flow=build(args.repository,args.number,args.title,args.skill_id,args.revision_id,args.runner_url)
    Path(args.output).write_text(json.dumps(flow,indent=2)+'\n',encoding='utf-8')
