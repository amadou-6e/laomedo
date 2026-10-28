"""Build the original-agent activity example; never dispatch model work."""
import argparse
import ast
import importlib.util
import json
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template
from laomedo.skills.registry.store import SkillStore

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def build(store, first='http://127.0.0.1:8765', parallel='http://127.0.0.1:8767'):
    reference=SkillStore(store).import_skill('graph-activity-verification',HERE/'skill')
    spec=importlib.util.spec_from_file_location('activity_edge_builder',ROOT/'examples/native-codex-node/build_flow.py')
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    def node(filename,identifier,values,x,y):
        code=(ROOT/'components/laomedo'/filename).read_text(encoding='utf-8')
        definition,_=build_custom_component_template(Component(_code=code))
        kind=next(item.name for item in ast.parse(code).body if isinstance(item,ast.ClassDef)
                  and any(isinstance(base,ast.Name) and base.id=='Component' for base in item.bases))
        for key,value in values.items():
            definition['template'][key]['value']=value
        return {'id':identifier,'type':'genericNode','position':{'x':x,'y':y},
                'data':{'id':identifier,'type':kind,'node':definition,'selected_output':'run' if filename=='codex_agent.py' else 'skill'}}
    skill=node('skill.py','Skill-readonly',{key:reference[key] for key in ('skill_id','revision_id')},0,150)
    common={'model':'gpt-6-luna','effort':'low','timeout_seconds':210}
    first_node=node('codex_agent.py','Codex-read-project',{**common,'operation':'fresh','runner_url':first,
        'task':'Read only the first six lines of README.md using one read-only shell command. Briefly describe its workflow. No edits, network access, other files or subagents.'},450,0)
    resume=node('codex_agent.py','Codex-follow-up',{**common,'operation':'resume','runner_url':first,
        'task':'Using the README context from the previous turn, describe its workflow in fifteen words or fewer. No tools, edits, network access or subagents.'},950,0)
    other=node('codex_agent.py','Codex-parallel-read',{**common,'operation':'fresh','runner_url':parallel,
        'task':'Read only the first six lines of README.md using one read-only shell command. Spawn exactly one child agent and pass that excerpt; ask it for the project title without tools. Wait and return its answer. No edits, network access, other files, or additional agents.'},450,500)
    return {'name':'Original Codex agents · concurrent turns','description':'Real Docker agents read the PR example. Two independent runners, a resumed thread, and one requested native child. No GitHub writes.',
        'flow_type':'workflow','access_type':'PRIVATE','data':{'nodes':[skill,first_node,resume,other],
        'edges':[helper.edge(skill,'skill',first_node,'skill_reference'),helper.edge(skill,'skill',other,'skill_reference'),
                 helper.edge(first_node,'run',resume,'run_reference')],
        'viewport':{'x':40,'y':40,'zoom':.65}}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill-store',type=Path,required=True)
    parser.add_argument('--runner-url',default='http://127.0.0.1:8765')
    parser.add_argument('--parallel-runner-url',default='http://127.0.0.1:8767')
    parser.add_argument('--output',type=Path,default=HERE/'flow.json')
    args=parser.parse_args()
    args.output.write_text(json.dumps(build(args.skill_store,args.runner_url,args.parallel_runner_url),indent=2)+'\n',encoding='utf-8')
    print('Original-agent graph exported; no model invoked.')
