"""Build a no-model Langflow 1.12.3 flow from the installed component API."""

from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


HERE = Path(__file__).resolve().parent
STARTER = Path("/app/.venv/lib64/python3.14/site-packages/langflow/initial_setup"
               "/starter_projects/Basic Prompting.json")


def edge(source, name, output, target, field, inputs):
    source_handle = {"dataType": name, "id": source, "name": output,
                     "output_types": ["Message"]}
    target_handle = {"fieldName": field, "id": target, "inputTypes": inputs,
                     "type": "str"}
    return {"id": f"{source}-{target}", "source": source, "target": target,
            "sourceHandle": json.dumps(source_handle),
            "targetHandle": json.dumps(target_handle),
            "data": {"sourceHandle": source_handle, "targetHandle": target_handle}}


def main():
    if version("langflow") != "1.12.3":
        raise RuntimeError("pinned Langflow 1.12.3 required")
    starter = json.loads(STARTER.read_text(encoding="utf-8"))
    nodes = starter["data"]["nodes"]
    chat_input = deepcopy(next(n for n in nodes if n.get("data", {}).get("type") == "ChatInput"))
    chat_output = deepcopy(next(n for n in nodes if n.get("data", {}).get("type") == "ChatOutput"))
    for node, node_id, x in ((chat_input, "ChatInput-exp03", 0),
                             (chat_output, "ChatOutput-exp03", 1000)):
        node["id"] = node_id
        node["data"]["id"] = node_id
        node["position"] = {"x": x, "y": 0}
    source = (HERE / "freeze_component.py").read_text(encoding="utf-8")
    imports, marker_class = source.split("class MarkerAfterPause", 1)
    pause_code = imports
    marker_code = source.split("class PauseForEdit", 1)[0] + "class MarkerAfterPause" + marker_class
    generated = []
    for code, node_id, node_type, x in (
        (pause_code, "Exp03Pause-exp03", "Exp03Pause", 300),
        (marker_code, "Exp03Marker-exp03", "Exp03Marker", 650),
    ):
        definition, _ = build_custom_component_template(Component(_code=code))
        if node_type == "Exp03Pause":
            definition["template"]["gate"]["value"] = "/experiment/release"
        else:
            definition["template"]["marker"]["value"] = "BEFORE"
        generated.append({"id": node_id, "type": "genericNode",
                          "position": {"x": x, "y": 0},
                          "data": {"id": node_id, "type": node_type,
                                   "node": definition, "selected_output": "result"}})
    pause, marker = generated
    flow = {"name": "EXP-03 graph freeze synthetic", "description": "No model calls.",
            "last_tested_version": "1.12.3", "flow_type": "workflow",
            "access_type": "PRIVATE",
            "data": {"nodes": [chat_input, pause, marker, chat_output],
                     "edges": [
                         edge(chat_input["id"], "ChatInput", "message", pause["id"], "task", ["Message"]),
                         edge(pause["id"], "Exp03Pause", "result", marker["id"], "value", ["Message"]),
                         edge(marker["id"], "Exp03Marker", "result", chat_output["id"],
                              "input_value", ["Data", "JSON", "DataFrame", "Table", "Message"]),
                     ], "viewport": {"x": 0, "y": 0, "zoom": 1}}}
    (HERE / "flow.json").write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")
    print("component_source_sha256=" + sha256(source.encode()).hexdigest())
    print("graph_sha256=" + sha256(json.dumps(flow["data"], sort_keys=True).encode()).hexdigest())


if __name__ == "__main__":
    main()
