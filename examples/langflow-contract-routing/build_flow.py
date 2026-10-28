"""Export the simplified graph; no model execution or external writes."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid5; from uuid import NAMESPACE_URL

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('legacy_demo', ROOT / 'examples/langflow-workgraph-demo/build_flow.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def build():
    flow = legacy.build()
    flow['id'] = str(uuid5(NAMESPACE_URL, 'laomedo-single-contract-routing-v1'))
    flow['name'] = 'Laomedo single Output Contract routes (simulated publication)'
    flow['description'] = 'One downstream contract with automatic native precheck binding. Credential-free fixtures; publication simulated.'
    nodes = [node for node in flow['data']['nodes'] if node['id'] not in {'requirements', 'routing'}]
    contract = legacy.node(ROOT / 'components/laomedo/output_contract.py', 'contract', {'requirements_json': json.dumps(legacy.FORM)}, 800, 0)
    nodes = [contract if node['id']=='contract' else node for node in nodes]
    by_id = {node['id']: node for node in nodes}
    by_id['contract']['position'] = {'x': 800, 'y': 0}
    # New exports show only integrated routes; legacy exports retain old ports.
    by_id['contract']['data']['node']['outputs'] = [o for o in by_id['contract']['data']['node']['outputs'] if o['name'] in {'success','failure','rejection','recovery'}]
    edges = [edge for edge in flow['data']['edges'] if edge['source'] not in {'requirements', 'routing'} and edge['target'] != 'routing']
    for key in ('success', 'failure', 'rejection', 'recovery'):
        edges.append(legacy.helper.edge(by_id['contract'], key, by_id[key], 'routed'))
        by_id[key]['position']['x'] = 1200
    flow['data'].update(nodes=nodes, edges=edges)
    from lfx.graph.graph.base import Graph
    Graph.from_payload(flow)
    return flow


if __name__ == '__main__':
    (HERE / 'flow.json').write_text(json.dumps(build(), indent=2)+'\n', encoding='utf-8')
