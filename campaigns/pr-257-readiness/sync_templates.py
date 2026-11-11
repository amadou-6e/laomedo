"""Refresh selected maintained Skill templates; preserve other graph values."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path("C:/CodeWorkspace/laomedo/.tools/worktrees/pr-257")
manifest = ROOT / "tests/contracts/component-templates.json"
contract = json.loads(manifest.read_text())
projection = json.loads(Path("C:/CodeWorkspace/laomedo/.tools/pr-readiness/257-private-flow.json").read_text())
fields = projection["data"]["nodes"][0]["data"]["node"]["template"]
changed = []
for record in contract["files"]:
    path = ROOT / record["path"]
    graph = json.loads(path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph.get("nodes", graph.get("data", {}).get("nodes", []))}
    touched = False
    for item in record["nodes"]:
        if item["component"] != "components/laomedo/skill.py":
            continue
        node = nodes[item["node_id"]]["data"]["node"]
        source = (ROOT / item["component"]).read_text(encoding="utf-8")
        node["template"]["code"]["value"] = source
        for name in ("github_connection", "private_repository_id"):
            node["template"][name] = deepcopy(fields[name])
        if item["has_code_hash"]:
            node["metadata"]["code_hash"] = sha256(source.encode()).hexdigest()[:12]
        touched = True
    if not touched:
        continue
    path.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    normalized = deepcopy(graph)
    normalized_nodes = {node["id"]: node for node in normalized.get("nodes", normalized.get("data", {}).get("nodes", []))}
    for item in record["nodes"]:
        definition = normalized_nodes[item["node_id"]]["data"]["node"]
        definition["template"]["code"]["value"] = "CURRENT_COMPONENT_SOURCE"
        if item["has_code_hash"]:
            definition["metadata"]["code_hash"] = "CURRENT_COMPONENT_HASH"
    record["graph_values_sha256"] = sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    changed.append(record["path"])
manifest.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"updated_maintained_graphs": changed, "private_defaults": "anonymous/empty"}))
