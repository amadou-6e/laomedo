"""Build and validate the native-node example in pinned Langflow, without a turn."""

from copy import deepcopy
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from lfx.custom.custom_component.component import Component
from lfx.custom.directory_reader.directory_reader import DirectoryReader
from lfx.custom.utils import build_custom_component_template
from lfx.graph.graph.base import Graph


ROOT = Path(__file__).resolve().parents[2]


def edge(source, name, target, field):
    output = next(item for item in source["data"]["node"]["outputs"]
                  if item["name"] == name)
    input_field = target["data"]["node"]["template"][field]
    outgoing = {"dataType": source["data"]["type"], "id": source["id"],
                "name": name, "output_types": output["types"]}
    incoming = {"fieldName": field, "id": target["id"],
                "inputTypes": input_field.get("input_types", []), "type": input_field["type"]}
    return {"id": source["id"] + "-" + target["id"], "source": source["id"],
            "target": target["id"], "sourceHandle": json.dumps(outgoing),
            "targetHandle": json.dumps(incoming),
            "data": {"sourceHandle": outgoing, "targetHandle": incoming}}


def main():
    path = ROOT / "components/laomedo/codex_agent.py"
    reader = DirectoryReader(str(ROOT / "components"))
    catalog = reader.build_component_menu_list([str(path)])
    entry = catalog["menu"][0]["components"][0]
    assert not entry["error"], entry["error"]
    assert catalog["menu"][0]["name"] == "laomedo"
    template, _ = build_custom_component_template(Component(_code=path.read_text()))
    skill_path = ROOT / "components/laomedo/skill.py"
    skill_template, _ = build_custom_component_template(Component(_code=skill_path.read_text()))
    old = json.loads((ROOT / "examples/skill-agent-pilot/pilot-flow.json").read_text())
    nodes = old["data"]["nodes"]
    chat_input = deepcopy(next(n for n in nodes if n["data"]["type"] == "ChatInput"))
    chat_output = deepcopy(next(n for n in nodes if n["data"]["type"] == "ChatOutput"))
    old_agent = next(n for n in nodes if n["data"]["type"] == "LaomedoRunner")
    for field in ["skill_id", "revision_id", "model", "effort"]:
        template["template"][field]["value"] = old_agent["data"]["node"]["template"][field]["value"]
    for field in ["skill_id", "revision_id"]:
        skill_template["template"][field]["value"] = template["template"][field]["value"]
        template["template"][field]["value"] = ""
    skill = {"id": "LaomedoSkill-native", "type": "genericNode",
             "position": {"x": 0, "y": 420},
             "data": {"id": "LaomedoSkill-native", "type": "LaomedoSkill",
                      "node": skill_template, "selected_output": "skill"}}
    agent = {"id": "LaomedoCodexAgent-native", "type": "genericNode",
             "position": {"x": 420, "y": 100},
             "data": {"id": "LaomedoCodexAgent-native", "type": "LaomedoCodexAgent",
                      "node": template, "selected_output": "answer"}}
    run_output = deepcopy(chat_output)
    run_output["id"] = run_output["data"]["id"] = "ChatOutput-run-reference"
    run_output["position"] = {"x": 850, "y": 400}
    flow = {"id": str(uuid5(NAMESPACE_URL, "laomedo-native-codex-node-v1")),
            "name": "Laomedo Skill and Codex Agent",
            "description": "Fresh/resume Codex custom component with shared answer/run outputs.",
            "last_tested_version": "1.12.3", "flow_type": "workflow", "access_type": "PRIVATE",
            "data": {"nodes": [chat_input, skill, agent, chat_output, run_output],
                     "edges": [
                         edge(chat_input, "message", agent, "task"),
                         edge(skill, "skill", agent, "skill_reference"),
                         edge(agent, "answer", chat_output, "input_value"),
                         edge(agent, "run", run_output, "input_value"),
                     ], "viewport": {"x": 0, "y": 0, "zoom": 1}}}
    graph = Graph.from_payload(flow)
    assert len(graph.vertices) == 5
    destination = Path(__file__).with_name("flow.json")
    destination.write_text(json.dumps(flow, indent=2) + "\n")
    print("directory_discovery_and_five_vertex_graph_passed")


if __name__ == "__main__":
    main()
