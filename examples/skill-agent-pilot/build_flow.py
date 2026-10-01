"""Build the pinned Langflow 1.12.3 flow from its installed node schemas.

Run this inside the pinned Langflow image with this directory mounted at /pilot.
"""

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


HERE = Path(__file__).resolve().parent
STARTER = Path("/app/.venv/lib64/python3.14/site-packages/langflow/initial_setup"
               "/starter_projects/Basic Prompting.json")


def edge(source_id, source_type, source_name, output_types,
         target_id, target_name, input_types):
    source = {"dataType": source_type, "id": source_id, "name": source_name,
              "output_types": output_types}
    target = {"fieldName": target_name, "id": target_id,
              "inputTypes": input_types, "type": "str"}
    return {"id": f"{source_id}-{target_id}", "source": source_id,
            "target": target_id, "sourceHandle": json.dumps(source),
            "targetHandle": json.dumps(target),
            "data": {"sourceHandle": source, "targetHandle": target}}


def main():
    starter = json.loads(STARTER.read_text(encoding="utf-8"))
    components = starter["data"]["nodes"]
    chat_input = deepcopy(next(n for n in components
                               if n.get("data", {}).get("type") == "ChatInput"))
    chat_output = deepcopy(next(n for n in components
                                if n.get("data", {}).get("type") == "ChatOutput"))
    for node, node_id, x in ((chat_input, "ChatInput-laomedo", 0),
                             (chat_output, "ChatOutput-laomedo", 850)):
        node["id"] = node_id
        node["data"]["id"] = node_id
        node["position"] = {"x": x, "y": 120}
    code = (HERE / "langflow_component.py").read_text(encoding="utf-8")
    definition, _ = build_custom_component_template(Component(_code=code))
    from hashlib import sha256
    content = (HERE / "skill" / "SKILL.md").read_bytes()
    digest = sha256()
    relative = b"SKILL.md"
    digest.update(len(relative).to_bytes(8, "big"))
    digest.update(relative)
    digest.update(len(content).to_bytes(8, "big"))
    digest.update(content)
    revision = "sha256:" + digest.hexdigest()
    definition["template"]["skill_id"]["value"] = "laomedo-pilot"
    definition["template"]["revision_id"]["value"] = revision
    definition["template"]["model"]["value"] = "gpt-6-luna"
    definition["template"]["effort"]["value"] = "low"
    custom = {"id": "LaomedoRunner-laomedo", "type": "genericNode",
              "position": {"x": 420, "y": 120},
              "data": {"id": "LaomedoRunner-laomedo", "type": "LaomedoRunner",
                       "node": definition, "selected_output": "result"}}
    flow = {"id": str(uuid5(NAMESPACE_URL, "laomedo-skill-agent-pilot-v1")),
            "name": "Laomedo pinned-skill Codex pilot v1",
            "description": "Local single-user Codex run with a pinned whole-skill revision.",
            "last_tested_version": "1.12.3",
            "flow_type": "workflow", "access_type": "PRIVATE",
            "data": {"nodes": [chat_input, custom, chat_output],
                     "edges": [
                         edge(chat_input["id"], "ChatInput", "message", ["Message"],
                              custom["id"], "task", ["Message"]),
                         edge(custom["id"], "LaomedoRunner", "result", ["JSON"],
                              chat_output["id"], "input_value",
                              ["Data", "JSON", "DataFrame", "Table", "Message"]),
                     ], "viewport": {"x": 0, "y": 0, "zoom": 1}}}
    (HERE / "pilot-flow.json").write_text(json.dumps(flow, indent=2) + "\n",
                                           encoding="utf-8")
    print(revision)


if __name__ == "__main__":
    main()
