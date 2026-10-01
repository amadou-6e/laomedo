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
    agent_template, _ = build_custom_component_template(Component(
        _code=(ROOT / "components/laomedo/codex_agent.py").read_text()))
    for name, field in a["data"]["node"]["template"].items():
        if name in agent_template["template"] and isinstance(field, dict) and "value" in field:
            if name != "code":
                agent_template["template"][name]["value"] = field["value"]
    a["data"]["node"] = agent_template
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
                helper.edge(handoff, "provenance", b, "handoff_reference"),
                helper.edge(skill, "skill", b, "skill_reference"), helper.edge(b, "answer", output, "input_value")],
                "viewport": {"x": 0, "y": 0, "zoom": .7}}}
    Graph.from_payload(flow)
    return flow


def build_controller(**values):
    original = json.loads((ROOT / "examples/native-codex-node/flow.json").read_text())
    template, _ = build_custom_component_template(Component(
        _code=(ROOT / "components/laomedo/bounded_controller.py").read_text()))
    for name, value in {"mode": "loop", "stop_answer": "DONE", **values}.items():
        template["template"][name]["value"] = value
    controller = {"id": "LaomedoBoundedController-loop", "type": "genericNode",
                  "position": {"x": 400, "y": 100},
                  "data": {"id": "LaomedoBoundedController-loop", "type": "LaomedoBoundedController",
                           "node": template, "selected_output": "execution"}}
    source = deepcopy(next(n for n in original["data"]["nodes"] if n["data"]["type"] == "ChatInput"))
    skill = deepcopy(next(n for n in original["data"]["nodes"] if n["data"]["type"] == "LaomedoSkill"))
    output = deepcopy(next(n for n in original["data"]["nodes"] if n["id"] == "ChatOutput-laomedo"))
    answer = deepcopy(output)
    answer["id"] = answer["data"]["id"] = "ChatOutput-loop-answer"
    answer["position"] = {"x": 800, "y": 350}
    flow = {"name": "Laomedo bounded agent loop", "description": "Explicit bounded controller; no cyclic visual edges.",
            "last_tested_version": "1.12.3", "flow_type": "workflow", "access_type": "PRIVATE",
            "data": {"nodes": [source, skill, controller, output, answer], "edges": [
                helper.edge(source, "message", controller, "task"), helper.edge(skill, "skill", controller, "skills"),
                helper.edge(controller, "execution", output, "input_value"),
                helper.edge(controller, "answer", answer, "input_value")],
                "viewport": {"x": 0, "y": 0, "zoom": 1}}}
    Graph.from_payload(flow)
    return flow


if __name__ == "__main__":
    Path(__file__).with_name("flow.json").write_text(json.dumps(build(), indent=2) + "\n")
    Path(__file__).with_name("loop-flow.json").write_text(json.dumps(build_controller(), indent=2) + "\n")
    print("six_vertex_chain_validated")
