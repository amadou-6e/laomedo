"""Build a synthetic Langflow 1.12.3 stage flow without model components."""

from copy import deepcopy
from importlib.metadata import version
import json
from pathlib import Path
import sys

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template

sys.path.insert(0, "/experiments")
from exp03.build_flow import STARTER, edge


HERE = Path(__file__).resolve().parent


def main():
    if version("langflow") != "1.12.3":
        raise RuntimeError("pinned Langflow 1.12.3 required")
    nodes = json.loads(STARTER.read_text(encoding="utf-8"))["data"]["nodes"]
    chat_input = deepcopy(next(n for n in nodes if n.get("data", {}).get("type") == "ChatInput"))
    chat_output = deepcopy(next(n for n in nodes if n.get("data", {}).get("type") == "ChatOutput"))
    for node, node_id, x in ((chat_input, "ChatInput-exp06", 0),
                             (chat_output, "ChatOutput-exp06", 700)):
        node["id"] = node_id
        node["data"]["id"] = node_id
        node["position"] = {"x": x, "y": 0}
    code = (HERE / "stage_component.py").read_text(encoding="utf-8")
    definition, _ = build_custom_component_template(Component(_code=code))
    definition["template"]["mode"]["value"] = "ui"
    stage = {"id": "Exp06Stage-exp06", "type": "genericNode",
             "position": {"x": 350, "y": 0},
             "data": {"id": "Exp06Stage-exp06", "type": "Exp06Stage",
                      "node": definition, "selected_output": "result"}}
    flow = {"name": "EXP-06 synthetic UI and backend death", "description": "No model calls.",
            "last_tested_version": "1.12.3", "flow_type": "workflow",
            "access_type": "PRIVATE",
            "data": {"nodes": [chat_input, stage, chat_output],
                     "edges": [edge(chat_input["id"], "ChatInput", "message", stage["id"],
                                    "task", ["Message"]),
                               edge(stage["id"], "Exp06Stage", "result", chat_output["id"],
                                    "input_value", ["Data", "JSON", "DataFrame", "Table", "Message"])],
                     "viewport": {"x": 0, "y": 0, "zoom": 1}}}
    (HERE / "flow.json").write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
