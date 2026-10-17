"""Export Skill → existing Codex Agent → same Skill Operation without execution."""
import argparse
import importlib.util
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from lfx.graph.graph.base import Graph
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('skill_operation_builder', ROOT/'examples/langflow-workgraph-demo/build_flow.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def build(skill_id, revision, editor_revision, runner_url, edit_request, commit_id=''):
    skill = builder.node(ROOT/'components/laomedo/skill.py', 'skill', {
        'source': '', 'skill_id': skill_id, 'revision_id': revision,
        'edit_request': edit_request, 'commit_id': commit_id}, 0, 0)
    for field, value in [('skill_id', skill_id), ('revision_id', revision)]:
        skill['data']['node']['template'][field]['options'] = [value]
    agent = builder.node(ROOT/'components/laomedo/codex_agent.py', 'agent', {
        'operation': 'fresh', 'skill_id': 'skill-operation-editor',
        'revision_id': editor_revision, 'runner_url': runner_url, 'output_retries': 0}, 600, 0)
    flow = {'id': str(uuid5(NAMESPACE_URL, 'laomedo-skill-operations-176')),
        'name': 'Skill → Codex Agent → same Skill Operation',
        'description': 'Atomic multi-file candidate; immutable commit history and diffs. No automatic promotion or Git publishing.',
        'last_tested_version': '1.12.3', 'flow_type': 'workflow', 'access_type': 'PRIVATE',
        'data': {'nodes': [skill, agent], 'edges': [builder.helper.edge(skill, 'task', agent, 'task'),
            builder.helper.edge(agent, 'answer', skill, 'operation')],
            'viewport': {'x': 60, 'y': 50, 'zoom': 0.8}}}
    Graph.from_payload(flow)
    return flow


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('skill-id', 'revision', 'editor-revision', 'runner-url', 'edit-request', 'output'):
        parser.add_argument('--'+field, required=True)
    parser.add_argument('--commit-id', default='')
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(build(args.skill_id, args.revision, args.editor_revision,
        args.runner_url, args.edit_request, args.commit_id), indent=2)+'\n', encoding='utf-8')
