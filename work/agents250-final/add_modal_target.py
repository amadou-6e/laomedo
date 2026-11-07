"""Add an unexecuted production Handoff node to inspect the actual code modal."""

import importlib.util
import json
from pathlib import Path

import langflow


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    source = root / ".tools/agent-refactor-205"
    e = root / "claude-review.local/agents-250-20261107"
    state = (
        Path(json.loads((e / "runtime-path.json").read_text(encoding="utf-8"))["path"])
        / "recovery-preview"
    )
    spec = importlib.util.spec_from_file_location(
        "graph_ports", source / "examples/graph.py"
    )
    ports = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ports)
    file = state / "flow.json"
    flow = json.loads(file.read_text(encoding="utf-8"))
    if any(node["id"] == "modal-target" for node in flow["data"]["nodes"]):
        raise SystemExit("Modal target already exists; preserved.")
    flow["data"]["nodes"].append(
        ports.node(
            source / "components/laomedo/handoff.py", "modal-target", {}, -450, 0
        )
    )
    file.write_text(json.dumps(flow), encoding="utf-8")
    print(
        json.dumps(
            {
                "production_component": "LaomedoHandoff",
                "scope": "Open code modal only; never execute Handoff",
                "model_turns_submitted": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
