"""Build the real two-node graph; never starts an Agent or provider call."""
import argparse,importlib.util,json
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from lfx.graph.graph.base import Graph
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('pr_original_builder',ROOT/'examples/langflow-workgraph-demo/build_flow.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def build(repository,number,title,revision,runner_url,skill_id='pr-feedback-title'):
    node,edge=builder.node,builder.helper.edge
    pr=node(ROOT/'components/laomedo/github_pr.py','pr',{
        'repository_url':'https://github.com/'+repository,'pr_choice':f'#{number} {title}',
        'labels':[],'state':'open'},0,0)
    agent=node(ROOT/'components/laomedo/codex_agent.py','agent',{
        'operation':'fresh','skill_id':skill_id,'revision_id':revision,
        'runner_url':runner_url,'output_retries':0},600,100)
    flow={'id':str(uuid5(NAMESPACE_URL,'laomedo-original-pr-feedback-170')),
        'name':'PR → original Codex Agent → same PR',
        'description':'Real Docker LocalRunner and live GitHub. Host-only feedback reservation; content-only Agent proposal.',
        'last_tested_version':'1.12.3','flow_type':'workflow','access_type':'PRIVATE',
        'data':{'nodes':[pr,agent],'edges':[edge(pr,'task',agent,'task'),edge(agent,'answer',pr,'operation')],
                'viewport':{'x':60,'y':50,'zoom':0.8}}}
    Graph.from_payload(flow)
    return flow


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('repository','title','revision','runner-url','output'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--number',type=int,required=True)
    parser.add_argument('--skill-id',default='pr-feedback-title')
    args=parser.parse_args()
    from lfx.services.deps import get_settings_service
    get_settings_service()
    flow=build(args.repository,args.number,args.title,args.revision,args.runner_url,args.skill_id)
    Path(args.output).write_text(json.dumps(flow,indent=2)+'\n',encoding='utf-8')
