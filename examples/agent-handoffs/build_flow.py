"""Generate acyclic two-agent chain using pinned Langflow port metadata."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template
from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
helper_spec = importlib.util.spec_from_file_location("native_flow_builder", ROOT / "examples/native-codex-node/build_flow.py")
helper = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helper)


def build():
    original = json.loads((ROOT / "examples/native-codex-node/flow.json").read_text())
    nodes = original["data"]["nodes"]
    a = deepcopy(next(n for n in nodes if n["data"]["type"] == "LaomedoCodexAgent"))
    b = deepcopy(a)
    b["id"] = b["data"]["id"] = "LaomedoCodexAgent-second"
    b["position"] = {"x": 1100, "y": 100}
    handoff_template, _ = build_custom_component_template(Component(
        _code=(ROOT / "components/laomedo/handoff.py").read_text()))
    handoff = {"id": "LaomedoHandoff-chain", "type": "genericNode", "position": {"x": 750, "y": 100},
               "data": {"id": "LaomedoHandoff-chain", "type": "LaomedoHandoff",
                        "node": handoff_template, "selected_output": "task_message"}}
    source = deepcopy(next(n for n in nodes if n["data"]["type"] == "ChatInput"))
    skill = deepcopy(next(n for n in nodes if n["data"]["type"] == "LaomedoSkill"))
    output = deepcopy(next(n for n in nodes if n["id"] == "ChatOutput-laomedo"))
    output["position"] = {"x": 1500, "y": 100}
    flow = {"name": "Laomedo two-agent explicit handoff", "description": "Fresh independent Codex chain; synthetic acceptance only.",
            "last_tested_version": "1.12.3", "flow_type": "workflow", "access_type": "PRIVATE",
            "data": {"nodes": [source, skill, a, handoff, b, output], "edges": [
                helper.edge(source, "message", a, "task"), helper.edge(skill, "skill", a, "skill_reference"),
                helper.edge(a, "run", handoff, "origin"), helper.edge(handoff, "task_message", b, "task"),
                helper.edge(skill, "skill", b, "skill_reference"), helper.edge(b, "answer", output, "input_value")],
                "viewport": {"x": 0, "y": 0, "zoom": .7}}}
    Graph.from_payload(flow)
    return flow


if __name__ == "__main__":
    Path(__file__).with_name("flow.json").write_text(json.dumps(build(), indent=2) + "\n")
    print("six_vertex_chain_validated")
