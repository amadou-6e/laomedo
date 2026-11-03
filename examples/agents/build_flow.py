"""Export current Agent lifecycle graphs without executing them."""

import argparse
import importlib.util
import json
from pathlib import Path

from lfx.graph.graph.base import Graph

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "maintained_graph_ports", ROOT / "examples/graph.py"
)
ports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports)


def build(
    *,
    provider,
    model,
    effort,
    runner_url,
    task,
    reference=None,
    workflow="fresh",
    follow_up=None,
):
    if provider not in {"codex", "claude", "opencode"}:
        raise ValueError("Select codex, claude or opencode.")
    if workflow not in {"fresh", "resume", "handoff"}:
        raise ValueError("Select fresh, resume or handoff.")
    if workflow == "resume" and not follow_up:
        raise ValueError("Resume requires an explicit follow-up task.")
    component = ROOT / "components/laomedo" / (provider + "_agent.py")
    values = {
        "model": model,
        "effort": effort,
        "runner_url": runner_url,
        "operation": "fresh",
        "task": task,
    }
    first = ports.node(component, "agent", values, 0, 0)
    nodes, edges = [first], []
    agents = [first]
    if workflow != "fresh":
        second = ports.node(
            component,
            "follow-up",
            {
                **values,
                "task": follow_up,
                "operation": "resume" if workflow == "resume" else "fresh",
            },
            800,
            0,
        )
        nodes.append(second)
        agents.append(second)
        if workflow == "resume":
            edges.append(ports.edge(first, "run", second, "run_reference"))
        else:
            if "handoff_reference" not in second["data"]["node"]["template"]:
                raise ValueError(
                    f"The {provider} component does not expose a provenance handoff input."
                )
            handoff = ports.node(
                ROOT / "components/laomedo/handoff.py",
                "handoff",
                {"task": follow_up or ""},
                400,
                0,
            )
            nodes.append(handoff)
            edges.extend(
                [
                    ports.edge(first, "run", handoff, "origin"),
                    ports.edge(handoff, "task_message", second, "task"),
                    ports.edge(handoff, "provenance", second, "handoff_reference"),
                ]
            )
    if reference is not None:
        pin = {name: reference[name] for name in ("skill_id", "revision_id")}
        skill = ports.node(ROOT / "components/laomedo/skill.py", "skill", pin, 0, 400)
        for name, value in pin.items():
            skill["data"]["node"]["template"][name]["options"] = [value]
        nodes.append(skill)
        edges.extend(
            ports.edge(skill, "skill", agent, "skill_reference") for agent in agents
        )
    flow = {
        "name": f"{provider.title()} Agent â€” {workflow}",
        "description": "Current component graph. Building does not execute an Agent.",
        "flow_type": "workflow",
        "access_type": "PRIVATE",
        "data": {
            "nodes": nodes,
            "edges": edges,
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }
    Graph.from_payload(flow)
    return flow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider", choices=("codex", "claude", "opencode"), required=True
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--runner-url", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument(
        "--workflow", choices=("fresh", "resume", "handoff"), default="fresh"
    )
    parser.add_argument("--follow-up")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    flow = build(
        provider=args.provider,
        model=args.model,
        effort=args.effort,
        runner_url=args.runner_url,
        task=args.task,
        workflow=args.workflow,
        follow_up=args.follow_up,
        reference=(
            json.loads(args.reference.read_text(encoding="utf-8"))
            if args.reference
            else None
        ),
    )
    args.output.write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")
    print("Graph structure validated; no Agent was executed.")


if __name__ == "__main__":
    main()
