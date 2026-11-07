"""Independently verify saved JSON merge content against immutable Git inputs."""

import hashlib
import json
import subprocess
from pathlib import Path


def blob(repo, revision, path):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", revision + ":" + path]
    )


def merge(base, ours, theirs, path="", conflicts=None):
    conflicts = [] if conflicts is None else conflicts
    if ours == theirs or theirs == base:
        return ours
    if ours == base:
        return theirs
    if isinstance(base, dict) and isinstance(ours, dict) and isinstance(theirs, dict):
        absent = object()
        result = {}
        for key in base.keys() | ours.keys() | theirs.keys():
            item = merge(
                base.get(key, absent),
                ours.get(key, absent),
                theirs.get(key, absent),
                path + "/" + key,
                conflicts,
            )
            if item is not absent:
                result[key] = item
        return result
    conflicts.append(path)
    return ours


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    repo = root / ".tools/agent-refactor-205"
    e = root / "claude-review.local/agents-250-20261107"
    ours = "e61f5ae3282f3f2bae37ba879ac748ecf6b99362"
    theirs = "bb25013523e37fbb108b51638be171e879eb3883"
    checkpoint = "53c3bf5ce40016d6e4675b0fbf9dced6a5e4306e"
    base = subprocess.check_output(
        ["git", "-C", str(repo), "merge-base", ours, theirs], text=True
    ).strip()
    maps = []
    for path in [
        "frontend/langflow-skill-viewer/node-error-catalog.json",
        "tools/migrations/module-paths.json",
        "tools/migrations/symbol-paths.json",
    ]:
        values = [
            json.loads(blob(repo, r, path))
            for r in [base, ours, theirs, checkpoint, "HEAD"]
        ]
        conflicts = []
        expected = merge(*values[:3], conflicts=conflicts)
        maps.append(
            {
                "path": path,
                "competing_values": conflicts,
                "merge_matches_independent_recursive_result": expected == values[3],
                "unchanged_since_merge": values[3] == values[4],
            }
        )
    source = blob(repo, checkpoint, "components/laomedo/skill.py").decode("utf-8")
    graphs = []
    for row in json.loads(
        (e / "saved-skill-code-resolution.json").read_text(encoding="utf-8")
    ):
        path = row["path"]
        before = json.loads(blob(repo, ours, path))
        after = json.loads(blob(repo, checkpoint, path))
        expected = json.loads(json.dumps(before))
        changed = []
        accepted = []
        try:
            incoming = json.loads(blob(repo, theirs, path))
        except subprocess.CalledProcessError:
            incoming = {"data": {"nodes": []}}
        incoming_nodes = {n["id"]: n for n in incoming["data"]["nodes"]}
        after_nodes = {n["id"]: n for n in after["data"]["nodes"]}
        for node in expected["data"]["nodes"]:
            if node["data"].get("type") == "LaomedoSkill":
                node["data"]["node"]["template"]["code"]["value"] = source
                node["data"]["node"]["metadata"]["code_hash"] = hashlib.sha256(
                    source.encode()
                ).hexdigest()[:12]
                changed.append(node["id"])
            elif node["id"] in incoming_nodes:
                # Clean Git merges can also carry accepted defining-import
                # corrections into embedded source. Admit only those exact
                # incoming code/hash fields, never an arbitrary node change.
                old = node["data"]["node"]
                new = incoming_nodes[node["id"]]["data"]["node"]
                actual = after_nodes[node["id"]]["data"]["node"]
                if (
                    old["template"]["code"]["value"] != new["template"]["code"]["value"]
                    and actual["template"]["code"]["value"]
                    == new["template"]["code"]["value"]
                ):
                    old["template"]["code"]["value"] = new["template"]["code"]["value"]
                    old["metadata"]["code_hash"] = new["metadata"]["code_hash"]
                    accepted.append(node["id"])
        graphs.append(
            {
                "path": path,
                "skill_nodes_updated": changed,
                "exact_accepted_develop_code_updates": accepted,
                "all_other_content_exactly_preserved": expected == after,
            }
        )
    result = {
        "base": base,
        "ours": ours,
        "theirs": theirs,
        "merge_checkpoint": checkpoint,
        "maps": maps,
        "graphs": graphs,
    }
    (e / "integration-content-audit.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))
    if any(
        m["competing_values"]
        or not m["merge_matches_independent_recursive_result"]
        or not m["unchanged_since_merge"]
        for m in maps
    ):
        raise SystemExit(1)
    if not all(g["all_other_content_exactly_preserved"] for g in graphs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
