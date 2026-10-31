"""Build a two-node Skill -> OpenCode graph using actual pinned component ports."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import laomedo

laomedo.__path__.append(str(ROOT / "components/laomedo"))
sys.path.insert(0, str(ROOT / "examples/native-codex-node"))
from build_flow import edge
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template
from lfx.graph.graph.base import Graph


def build(reference, *, model, runner_url):
    def node(kind, identity, position):
        filename = {
            "LaomedoSkill": "skill.py",
            "LaomedoOpenCodeAgent": "opencode_agent.py",
        }[kind]
        code = (ROOT / "components/laomedo" / filename).read_text(encoding="utf8")
        template, _ = build_custom_component_template(Component(_code=code))
        return {
            "id": identity,
            "type": "genericNode",
            "position": position,
            "data": {
                "id": identity,
                "type": kind,
                "node": template,
                "selected_output": "skill" if kind == "LaomedoSkill" else "answer",
            },
        }

    skill = node("LaomedoSkill", "OpenCode-pinned-skill", {"x": 0, "y": 180})
    agent = node("LaomedoOpenCodeAgent", "OpenCode-read-project", {"x": 440, "y": 80})
    for field in ("skill_id", "revision_id"):
        skill["data"]["node"]["template"][field]["value"] = reference[field]
        skill["data"]["node"]["template"][field]["options"] = [reference[field]]
    fields = agent["data"]["node"]["template"]
    for name, value in {
        "model": model,
        "effort": "default",
        "runner_url": runner_url,
        "operation": "fresh",
        "task": "Load the graph-activity-verification skill. Use the isolated command worker to run exactly this command (no changes or trailing punctuation): `head -n 6 README.md`. Explain the PR workflow from those lines in one short paragraph. Do not edit files, invoke subagents, or use unrelated tools.",
    }.items():
        fields[name]["value"] = value
    agent["data"]["node"]["display_name"] = "OpenCode read project"
    flow = {
        "name": "OpenCode agent - real Docker lifecycle",
        "description": "Pinned Skill -> OpenCode. Activity shows native HTTP message snapshots; opening Activity never executes the graph.",
        "last_tested_version": "1.12.3",
        "flow_type": "workflow",
        "access_type": "PRIVATE",
        "data": {
            "nodes": [skill, agent],
            "edges": [edge(skill, "skill", agent, "skill_reference")],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }
    from lfx.services.manager import get_service_manager
    from lfx.services.schema import ServiceType
    from lfx.services.settings.service import SettingsService

    manager = get_service_manager()
    if ServiceType.SETTINGS_SERVICE not in manager.services:
        manager.services[ServiceType.SETTINGS_SERVICE] = SettingsService.initialize()
    Graph.from_payload(flow)
    return flow


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--runner-url", required=True)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("flow.json")
    )
    args = parser.parse_args()
    flow = build(
        json.loads(args.reference.read_text(encoding="utf8")),
        model=args.model,
        runner_url=args.runner_url,
    )
    args.output.write_text(json.dumps(flow, indent=2) + "\n", encoding="utf8")
    print("Validated two-node OpenCode graph; no agent invoked.")
