"""Wire the pinned production Load JSON component into the ordinary Operation input."""
import importlib.util,json,sys
from pathlib import Path
from uuid import uuid4
import langflow
from lfx.graph.graph.base import Graph


def main():
 kind=sys.argv[1];assert kind in {'issue','pr'};root=Path('C:/CodeWorkspace/laomedo');e=root/'claude-review.local/github-249-20261106';state=Path(json.loads((e/'runtime-path.json').read_text())['path']);targets=json.loads((state/'live-targets.json').read_text());spec=importlib.util.spec_from_file_location('maintained_graph',root/'.tools/github-restored-245/examples/graph.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder);flow=json.loads((state/('live-issue-flow.json' if kind=='issue' else 'pr-flow.json')).read_text());flow['id']=str(uuid4());flow['name']='GitHub '+kind+' ordinary Operation';resource=flow['data']['nodes'][0];template=resource['data']['node']['template'];choice='#'+str(targets[kind]['number'])+' '+('Original Codex Agent feedback verified' if kind=='pr' else targets[kind]['title']);template[kind+'_choice'].update(value=choice,options=[choice]);template['operation']['value']=None
 operation=json.loads((state/(kind+'-request.json')).read_text());node=builder.node(root/'.tools/github-only-upstream/src/lfx/src/lfx/components/data_source/json_to_data.py','operation',{'json_file':'','json_path':'','json_string':json.dumps(operation)},-500,0);flow['data']['nodes'].append(node);flow['data']['edges']=[builder.edge(node,'data',resource,'operation')];flow['data']['viewport']={'x':400,'y':70,'zoom':0.7};Graph.from_payload(flow);(state/(kind+'-ordinary-flow.json')).write_bytes(json.dumps(flow).encode())

if __name__=='__main__':main()
