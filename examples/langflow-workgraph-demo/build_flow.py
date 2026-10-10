"""Export the credential-free demo with real component port metadata."""
import importlib.util
import ast
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template
from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
helper_spec = importlib.util.spec_from_file_location("native_builder", ROOT / "examples/native-codex-node/build_flow.py")
helper = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helper)
FORM = {"schema_version": 1, "fields": [{"name": "task_outcome", "type": "string", "required": True,
                                        "checks": {"enum": ["success", "failure"]}},
                                      {"name": "report", "type": "string", "required": True,
                                      "checks": {"nonempty": True}}]}
SKILL = "sha256:" + hashlib.sha256((HERE / "skill/SKILL.md").read_bytes()).hexdigest()


def node(path, identifier, values, x, y):
    code = path.read_text(encoding="utf-8")
    template, _ = build_custom_component_template(Component(_code=code))
    component_type = next(item.name for item in ast.parse(code).body
                          if isinstance(item, ast.ClassDef) and any(
                              isinstance(base, ast.Name) and base.id == "Component" for base in item.bases))
    for name, value in values.items():
        template["template"][name]["value"] = value
    return {"id": identifier, "type": "genericNode", "position": {"x": x, "y": y},
            "data": {"id": identifier, "type": component_type, "node": template}}


def build():
    issue = node(HERE / "fixture_issue.py", "issue", {"issue_json": (HERE / "fixtures.json").read_text()}, 0, 0)
    skill = node(ROOT / "components/laomedo/skill.py", "skill", {"skill_id": "demo-report", "revision_id": SKILL}, 0, 300)
    agent = node(ROOT / "components/laomedo/codex_agent.py", "agent", {"operation": "fresh", "runner_url": "http://127.0.0.1:8765", "model": "fixture", "effort": "low"}, 400, 0)
    contract = node(ROOT / "components/laomedo/output_contract.py", "contract", {"requirements_json": json.dumps(FORM)}, 800, 0)
    requirements = node(ROOT / "components/laomedo/output_contract.py", "requirements", {"requirements_json": json.dumps(FORM)}, 0, 600)
    route = node(HERE / "route.py", "routing", {}, 1200, 0)
    destinations = [node(HERE / "destination.py", key, {"destination": key}, 1600, index * 300)
                    for index, key in enumerate(("success", "failure", "rejection"))]
    edges = [helper.edge(issue, "task", agent, "task"), helper.edge(skill, "skill", agent, "skill_reference"),
             helper.edge(agent, "submission", contract, "agent_submission"),
             helper.edge(contract, "validation", route, "validation")]
    has_precheck = "output_requirements" in agent["data"]["node"]["template"]
    if not has_precheck:
        raise ValueError("agent_output_requirements_port_required")
    edges.append(helper.edge(requirements, "requirements", agent, "output_requirements"))
    for destination in destinations:
        edges.extend([helper.edge(route, destination["id"], destination, "routed"),
                      helper.edge(issue, "snapshot", destination, "snapshot")])
    flow = {"id": str(uuid5(NAMESPACE_URL, "laomedo-workgraph-fixture-demo-v1")),
            "name": "Laomedo issue to contract routes (simulated publication)",
            "description": "Credential-free fixture. All publication references are simulated; no GitHub writes or model turns.",
            "last_tested_version": "1.12.3", "flow_type": "workflow", "access_type": "PRIVATE",
            "data": {"nodes": [issue, skill, requirements, agent, contract, route, *destinations],
                     "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": .7}}}
    Graph.from_payload(flow)
    return flow


if __name__ == "__main__":
    (HERE / "flow.json").write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print("demo_export_validated")
