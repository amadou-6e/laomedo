"""Generate actual pinned Langflow port handles for the OpenCode example."""

from copy import deepcopy
import json
from pathlib import Path
import sys

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template
from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "components"))
sys.path.insert(0, str(ROOT / "examples/native-codex-node"))
from build_flow import edge


def main():
    flow = json.loads((ROOT / "examples/native-codex-node/flow.json").read_text())
    template, _ = build_custom_component_template(Component(_code=(ROOT / "components/laomedo/opencode_agent.py").read_text()))
    node = next(item for item in flow["data"]["nodes"] if item["data"]["type"] == "LaomedoCodexAgent")
    old_fields = node["data"]["node"]["template"]
    for name, field in template["template"].items():
        if (isinstance(field, dict) and isinstance(old_fields.get(name), dict) and
                name not in {"code", "model", "effort", "runner_url"}):
            field["value"] = deepcopy(old_fields[name].get("value", ""))
    for name, value in {"model": "opencode-go/gpt-6-luna", "effort": "default",
                        "runner_url": "http://host.docker.internal:8768"}.items():
        template["template"][name]["value"] = value
    node["data"]["node"] = template
    node["data"]["type"] = "LaomedoOpenCodeAgent"
    node["data"]["selected_output"] = "answer"
    nodes = {item["id"]: item for item in flow["data"]["nodes"]}
    edges = []
    for current in flow["data"]["edges"]:
        source = nodes[current["source"]]
        target = nodes[current["target"]]
        outgoing = current["data"]["sourceHandle"]["name"]
        incoming = current["data"]["targetHandle"]["fieldName"]
        edges.append(edge(source, outgoing, target, incoming))
    flow["data"]["edges"] = edges
    flow["name"] = "Laomedo OpenCode isolated skills 27"
    flow.pop("id", None)
    Graph.from_payload(flow["data"])
    (ROOT / "examples/opencode-agent/flow.json").write_text(json.dumps(flow, indent=2) + "\n")
    print(json.dumps({"nodes": len(nodes), "edges": len(edges), "validated": True}))


if __name__ == "__main__":
    main()
