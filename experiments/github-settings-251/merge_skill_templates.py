"""Port only connection inputs into current maintained skill-node wire examples."""

import hashlib
import json
from pathlib import Path
import subprocess

root = Path("C:/CodeWorkspace/laomedo/.tools/worktrees/github-settings-251")
contract_path = root / "tests/contracts/component-templates.json"
contract = json.loads(contract_path.read_text(encoding="utf-8"))
old_paths = {
    "tests/test_agents/test_examples/data/claude.json": "examples/claude-agent/flow.json",
    "tests/test_agents/test_examples/data/codex.json": "examples/native-codex-node/flow.json",
    "tests/test_agents/test_examples/data/opencode.json": "examples/opencode-node/flow.json",
}
source = (root / "components/laomedo/skill.py").read_text(encoding="utf-8")
fields = ("github_connection", "private_repository_id")
for record in contract["files"]:
    if not any(
        item["component"] == "components/laomedo/skill.py" for item in record["nodes"]
    ):
        continue
    path = record["path"]
    graph_path = root / path
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", graph.get("data", {}).get("nodes", []))
    previous = json.loads(
        subprocess.check_output(
            ["git", "show", "HEAD:" + old_paths.get(path, path)], cwd=root
        )
    )
    previous_nodes = previous.get("nodes", previous.get("data", {}).get("nodes", []))
    old_skills = [
        n
        for n in previous_nodes
        if all(
            name in n.get("data", {}).get("node", {}).get("template", {})
            for name in fields
        )
    ]
    if not old_skills:
        raise RuntimeError("old_skill_template_not_found: " + path)
    for item in record["nodes"]:
        if item["component"] != "components/laomedo/skill.py":
            continue
        node = next(n for n in nodes if n["id"] == item["node_id"])
        definition = node["data"]["node"]
        old = next((n for n in old_skills if n["id"] == node["id"]), old_skills[0])
        old_template = old["data"]["node"]["template"]
        for name in fields:
            definition["template"][name] = old_template[name]
        definition["template"]["code"]["value"] = source
        if item["has_code_hash"]:
            definition["metadata"]["code_hash"] = hashlib.sha256(
                source.encode()
            ).hexdigest()[:12]
    graph_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for item in record["nodes"]:
        definition = next(n for n in nodes if n["id"] == item["node_id"])["data"][
            "node"
        ]
        if item["has_code_hash"]:
            definition["metadata"]["code_hash"] = "CURRENT_COMPONENT_HASH"
        definition["template"]["code"]["value"] = "CURRENT_COMPONENT_SOURCE"
    record["graph_values_sha256"] = hashlib.sha256(
        json.dumps(
            graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    print(path)
contract_path.write_text(
    json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
