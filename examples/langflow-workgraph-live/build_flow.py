"""Prepare an imported live graph. Building never starts a service or agent."""
import importlib.util
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from lfx.graph.graph.base import Graph
from laomedo.skill_store import inventory, tree_hash

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEMO = ROOT / "examples/langflow-workgraph-demo"
SKILL = tree_hash(inventory(HERE / "skill"))
spec = importlib.util.spec_from_file_location("workgraph_demo_builder", DEMO / "build_flow.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def build(snapshot, task, *, runner_url, model="gpt-6-luna", output_retries=1):
    node, edge = builder.node, builder.helper.edge
    issue = node(HERE / "frozen_issue.py", "issue",
                 {"snapshot_json": json.dumps(snapshot), "task_instruction": task}, 0, 0)
    skill = node(ROOT / "components/laomedo/skill.py", "skill",
                 {"skill_id": "live-report", "revision_id": SKILL}, 0, 300)
    requirements = node(ROOT / "components/laomedo/output_contract.py", "requirements",
                        {"requirements_json": json.dumps(builder.FORM)}, 0, 600)
    agent = node(ROOT / "components/laomedo/codex_agent.py", "agent",
                 {"operation": "fresh", "runner_url": runner_url, "model": model,
                  "effort": "low", "output_retries": output_retries}, 400, 0)
    contract = node(ROOT / "components/laomedo/output_contract.py", "contract",
                    {"requirements_json": json.dumps(builder.FORM)}, 800, 0)
    route = node(DEMO / "route.py", "routing", {}, 1200, 0)
    accepted = node(HERE / "accepted_validation.py", "accepted", {}, 1500, 0)
    publisher = node(ROOT / "components/laomedo/pr_publisher.py", "publisher",
                     {"runner_url": runner_url}, 1800, 0)
    destinations = [node(DEMO / "destination.py", key, {"destination": key}, 1600, i * 300 + 300)
                    for i, key in enumerate(("failure", "rejection", "recovery"))]
    edges = [edge(issue, "task", agent, "task"), edge(skill, "skill", agent, "skill_reference"),
             edge(requirements, "requirements", agent, "output_requirements"),
             edge(agent, "submission", contract, "agent_submission"),
             edge(contract, "validation", route, "validation"),
             edge(route, "success", accepted, "routed"),
             edge(accepted, "validation", publisher, "validation")]
    for target in destinations:
        edges.extend([edge(route, target["id"], target, "routed"),
                      edge(issue, "snapshot", target, "snapshot")])
    flow = {"id": str(uuid5(NAMESPACE_URL, "laomedo-live-workgraph-v1")),
            "name": "Laomedo frozen issue to trusted draft publisher",
            "description": "Explicitly configured local live graph. The host owns the finite grant and publisher; no GitHub credential enters the graph.",
            "last_tested_version": "1.12.3", "flow_type": "workflow", "access_type": "PRIVATE",
            "data": {"nodes": [issue, skill, requirements, agent, contract, route, accepted, publisher, *destinations],
                     "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": .6}}}
    Graph.from_payload(flow)
    return flow
