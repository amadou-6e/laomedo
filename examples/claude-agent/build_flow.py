"""Build Skill -> Claude -> same Skill Operation with an independent Skill pin."""
import importlib.util
import json
from pathlib import Path

import laomedo
from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
laomedo.__path__.append(str(ROOT / 'components/laomedo'))
spec = importlib.util.spec_from_file_location('skill_builder', ROOT / 'examples/skill-operations/build_flow.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def build(skill_id, revision, editor_revision, runner_url, edit_request):
    flow = builder.build(skill_id, revision, editor_revision, runner_url, edit_request)
    values = flow['data']['nodes'][1]['data']['node']['template']
    agent = builder.builder.node(ROOT / 'components/laomedo/claude_agent.py', 'agent', {
        'operation': 'fresh', 'runner_url': runner_url, 'model': 'sonnet', 'effort': 'low',
        'output_requirements_json': values['output_requirements_json']['value'],
        'output_retries': 1}, 600, 0)
    skill = flow['data']['nodes'][0]
    flow.update(name='Skill -> Claude Code -> same Skill Operation',
                description='Real subscription-backed Claude proposal; host records immutable history.')
    flow.pop('id', None)
    flow['data']['nodes'][1] = agent
    editor = flow['data']['nodes'][2]
    flow['data']['edges'] = [builder.builder.helper.edge(skill, 'task', agent, 'task'),
                             builder.builder.helper.edge(agent, 'answer', skill, 'operation'),
                             builder.builder.helper.edge(editor, 'skill', agent, 'skill_reference')]
    Graph.from_payload(flow)
    return flow
