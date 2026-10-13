"""Create an importable real-port graph; building performs no dispatch."""
import importlib.util
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pr_graph_builder', ROOT / 'examples/langflow-workgraph-demo/build_flow.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


def build():
    node, edge = builder.node, builder.helper.edge
    reader = node(ROOT / 'components/laomedo/github_pr.py', 'read-pr',
        {'repository_url':'https://github.com/owner/repo', 'labels':[], 'state':'open', 'pr_choice':'#1 Change 1'}, 0, 0)
    operation = node(HERE / 'operation.py', 'operation', {}, 0, 550)
    writer = node(ROOT / 'components/laomedo/github_pr.py', 'apply-operation',
        {'repository_url':'https://github.com/owner/repo', 'labels':[], 'state':'open', 'pr_choice':''}, 500, 180)
    result = node(HERE / 'result.py', 'inspect-result', {}, 1000, 180)
    flow = {'id':str(uuid5(NAMESPACE_URL, 'laomedo-pr-operation-fixture-v1')),
        'name':'GitHub PR selection and incoming modify operation (fixture)',
        'description':'Injected fake GitHub provider; no model calls or live writes. Select/view a PR, pass its reference, apply a scoped operation, inspect its result.',
        'last_tested_version':'1.12.3', 'flow_type':'workflow', 'access_type':'PRIVATE',
        'data':{'nodes':[reader, operation, writer, result], 'edges':[
            edge(reader, 'pr', writer, 'pr_reference'), edge(operation, 'operation', writer, 'operation'),
            edge(writer, 'operation_result', result, 'result')], 'viewport':{'x':20,'y':20,'zoom':0.65}}}
    Graph.from_payload(flow)
    return flow


if __name__ == '__main__':
    (HERE / 'flow.json').write_text(json.dumps(build(), indent=2) + '\n', encoding='utf-8')
    print('pr_operation_graph_exported')
