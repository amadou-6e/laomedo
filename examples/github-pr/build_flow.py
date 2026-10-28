"""Export one PR and one Agent connected by native Langflow feedback handles."""
import importlib.util
import json
from pathlib import Path
from uuid import NAMESPACE_URL; from uuid import uuid5
from lfx.graph.graph.base import Graph
from lfx.services.deps import get_settings_service

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pr_graph_builder', ROOT / 'examples/langflow-workgraph-demo/build_flow.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


def build(action='modify'):
    get_settings_service()
    node, edge = builder.node, builder.helper.edge
    pr = node(ROOT / 'components/laomedo/github_pr.py', 'pr',
        {'repository_url':'https://github.com/owner/repo', 'labels':[], 'state':'open', 'pr_choice':'#1 Change 1'}, 0, 0)
    agent = node(HERE / 'agent.py','agent',{'action':action},600,120)
    source = {'dataType':'PRFixtureAgent','id':'agent','name':'operation','output_types':['Data']}
    target = {'id':'pr','fieldName':'operation','inputTypes':['Data','Message'],'type':'other'}
    feedback = {'id':'agent-operation-pr-task','source':'agent','target':'pr',
        'sourceHandle':json.dumps(source),'targetHandle':json.dumps(target),
        'data':{'sourceHandle':source,'targetHandle':target}}
    flow = {'id':str(uuid5(NAMESPACE_URL, 'laomedo-pr-agent-roundtrip-v2')),
        'name':'PR to Agent to same PR (fixture)',
        'description':'Two nodes. PR reads once, the deterministic Agent returns one operation, that same PR applies it and stops. No model turns or real GitHub writes.',
        'last_tested_version':'1.12.3', 'flow_type':'workflow', 'access_type':'PRIVATE',
        'data':{'nodes':[pr,agent], 'edges':[edge(pr,'task',agent,'task'),feedback],
                'viewport':{'x':80,'y':40,'zoom':0.8}}}
    Graph.from_payload(flow)
    return flow


if __name__ == '__main__':
    (HERE / 'flow.json').write_text(json.dumps(build(), indent=2) + '\n', encoding='utf-8')
    print('two_node_pr_agent_loop_exported')
