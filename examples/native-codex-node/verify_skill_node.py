import importlib.util
import argparse
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser(description="Verify installed Skill-to-Agent wiring with one authorized turn.")
parser.add_argument('--approved-model-turn', action='store_true')
args = parser.parse_args()
if not args.approved_model_turn:
    parser.error('requires separate bounded authorization and --approved-model-turn')
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('acceptance_helpers', root / 'examples/native-codex-node/acceptance.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
for _ in range(15):
    try:
        token = api.login()
        break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError('server_not_ready')
catalog = api.call(api.BASE + '/api/v1/all', token=token)
assert catalog['http'] == 200
assert all(name in json.dumps(catalog['body']) for name in ['LaomedoSkill', 'LaomedoCodexAgent'])
flow = json.loads((root / 'examples/native-codex-node/flow.json').read_text())
flow.pop('id', None)
agent = next(n for n in flow['data']['nodes'] if n['data']['type'] == 'LaomedoCodexAgent')
agent['data']['node']['template']['runner_url']['value'] = 'http://host.docker.internal:8766'
imported = api.call(api.BASE + '/api/v1/flows/', flow, token=token)
assert imported['http'] in [200, 201]
flow_id = imported['body']['id']
api.save('skill-node-flow', {'flow_id': flow_id})
print('installed_skill_node_and_flow_import_passed', flush=True)
before = set(api.records())
before_count = json.loads((api.STATE / 'turn-ledger.json').read_text())['attempted_turns']
key = api.call(api.BASE + '/api/v1/api_key/', {'name': 'skill-node-local-test'}, token=token)['body']['api_key']
response = api.call(api.BASE + '/api/v1/run/' + flow_id, {
    'input_value': 'Read /draft/.agents/skills/laomedo-pilot/SKILL.md and /draft/fixture.txt with shell tools. Report the sample color and the sample count stored in the file. Do not change files.',
    'input_type': 'chat', 'output_type': 'chat'}, token=token, api_key=key)
api.save('skill-node-response', response)
assert response['http'] == 200, 'skill_node_flow_failed'
after = api.records()
added = set(after) - before
assert len(added) == 1, 'duplicate_dispatch'
record = after[added.pop()]
assert record['status'] == 'completed' and record['attempt_number'] == before_count + 1
assert record['skill']['revision_id'] == next(n for n in flow['data']['nodes'] if n['data']['type'] == 'LaomedoSkill')['data']['node']['template']['revision_id']['value']
commands = [e['params']['item'] for e in api.events(record['run_id']) if e.get('method') == 'item/completed' and e.get('params', {}).get('item', {}).get('type') == 'commandExecution']
assert commands and any('The sample color is amber' in (item.get('aggregatedOutput') or '') for item in commands)
summary = {'catalog_nodes_verified': True, 'flow_id': flow_id, 'run_id': record['run_id'], 'thread_id': record['thread_id'], 'status': record['status'], 'skill_revision': record['skill']['revision_id'], 'native_command_results': len(commands), 'ledger': json.loads((api.STATE / 'turn-ledger.json').read_text())}
(root / 'examples/native-codex-node/skill-node-evidence.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
