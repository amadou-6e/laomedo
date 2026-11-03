"""Build current GitHub graphs from real selected references, without execution."""

import argparse
import importlib.util
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from lfx.graph.graph.base import Graph
from lfx.services.deps import get_settings_service
from laomedo.github.contract import validate_repository

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "github_example_graph", ROOT / "examples/graph.py"
)
graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph)


def build(
    repository,
    number,
    title,
    *,
    kind="pr",
    feedback=False,
    runner_url="",
    skill_id="",
    revision="",
):
    """Select one resource; optionally connect its existing bounded Agent feedback."""
    validate_repository(repository)
    if type(number) is not int or number < 1 or not title.strip():
        raise ValueError("Supply a positive resource number and its current title")
    if kind not in {"issue", "pr"}:
        raise ValueError("kind must be issue or pr")
    if feedback and (kind != "pr" or not all((runner_url, skill_id, revision))):
        raise ValueError("PR feedback needs runner URL and a pinned instruction skill")
    get_settings_service()
    resource = graph.node(
        ROOT / "components/laomedo" / ("github_" + kind + ".py"),
        kind,
        {
            "repository_url": "https://github.com/" + repository,
            kind + "_choice": f"#{number} {title}",
            "labels": [],
            "state": "open",
        },
        0,
        0,
    )
    resource["data"]["node"]["template"][kind + "_choice"]["options"] = [
        f"#{number} {title}"
    ]
    nodes, edges = [resource], []
    if feedback:
        agent = graph.node(
            ROOT / "components/laomedo/codex_agent.py",
            "agent",
            {"operation": "fresh", "runner_url": runner_url, "output_retries": 0},
            600,
            80,
        )
        skill = graph.node(
            ROOT / "components/laomedo/skill.py",
            "instructions",
            {"skill_id": skill_id, "revision_id": revision},
            0,
            800,
        )
        for field in ("skill_id", "revision_id"):
            value = skill["data"]["node"]["template"][field]
            value["options"] = [value["value"]]
        nodes.extend([agent, skill])
        edges.extend(
            [
                graph.edge(resource, "task", agent, "task"),
                graph.edge(agent, "answer", resource, "operation"),
                graph.edge(skill, "skill", agent, "skill_reference"),
            ]
        )
    flow = {
        "id": str(
            uuid5(
                NAMESPACE_URL, f"laomedo-github-{kind}-{repository}-{number}-{feedback}"
            )
        ),
        "name": (
            "GitHub PR and Agent feedback"
            if feedback
            else "GitHub " + kind + " inspection"
        ),
        "description": "Production components with an explicit selected reference. Building does not execute a model or GitHub operation.",
        "last_tested_version": "1.12.3",
        "flow_type": "workflow",
        "access_type": "PRIVATE",
        "data": {
            "nodes": nodes,
            "edges": edges,
            "viewport": {"x": 60, "y": 30, "zoom": 0.6 if feedback else 0.8},
        },
    }
    Graph.from_payload(flow)
    return flow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="Real owner/repository")
    parser.add_argument("--number", required=True, type=int)
    parser.add_argument(
        "--title", required=True, help="Current selected resource title"
    )
    parser.add_argument("--kind", choices=("issue", "pr"), default="pr")
    parser.add_argument("--feedback", action="store_true")
    parser.add_argument("--runner-url", default="")
    parser.add_argument("--skill-id", default="")
    parser.add_argument("--revision", default="")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    flow = build(
        args.repository,
        args.number,
        args.title,
        kind=args.kind,
        feedback=args.feedback,
        runner_url=args.runner_url,
        skill_id=args.skill_id,
        revision=args.revision,
    )
    args.output.write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
