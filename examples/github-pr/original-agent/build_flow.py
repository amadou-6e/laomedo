"""Build the real two-node graph; never starts an Agent or provider call."""
import importlib.util
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from lfx.graph.graph.base import Graph
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('pr_original_builder',ROOT/'examples/langflow-workgraph-demo/build_flow.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def build(repository,number,title,revision,runner_url):
    node,edge=builder.node,builder.helper.edge
    pr=node(ROOT/'components/laomedo/github_pr.py','pr',{
        'repository_url':'https://github.com/'+repository,'pr_choice':f'#{number} {title}',
        'labels':[],'state':'open'},0,0)
    agent=node(ROOT/'components/laomedo/codex_agent.py','agent',{
        'operation':'fresh','skill_id':'pr-feedback-proposal','revision_id':revision,
        'runner_url':runner_url,'output_retries':0},600,100)
    flow={'id':str(uuid5(NAMESPACE_URL,'laomedo-original-pr-feedback-170')),
        'name':'PR → original Codex Agent → same PR',
        'description':'Real Docker LocalRunner and live GitHub. Host-only feedback reservation; content-only Agent proposal.',
        'last_tested_version':'1.12.3','flow_type':'workflow','access_type':'PRIVATE',
        'data':{'nodes':[pr,agent],'edges':[edge(pr,'task',agent,'task'),edge(agent,'answer',pr,'operation')],
                'viewport':{'x':60,'y':50,'zoom':0.8}}}
    Graph.from_payload(flow)
    return flow
