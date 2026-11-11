"""Fresh production Skill component projection; never build or run the graph."""

import json
from pathlib import Path
import sys
from uuid import uuid4

import langflow

ROOT = Path("C:/CodeWorkspace/laomedo")
sys.path.insert(0, str(ROOT / ".tools/worktrees/pr-257/components/laomedo"))
from skill import LaomedoSkill

component = LaomedoSkill()
projected = component.to_frontend_node()["data"]["node"]
flow = {
    "id": str(uuid4()),
    "name": "Private Skill read-only QA",
    "description": "Fresh production component; no graph execution or credentials.",
    "last_tested_version": "1.12.3",
    "flow_type": "workflow",
    "access_type": "PRIVATE",
    "data": {
        "nodes": [{"id": "skill", "type": "genericNode", "position": {"x": 0, "y": 0},
                   "data": {"id": "skill", "type": "LaomedoSkill", "node": projected}}],
        "edges": [],
        "viewport": {"x": 400, "y": 70, "zoom": 1},
    },
}
(ROOT / ".tools/pr-readiness/257-private-flow.json").write_text(json.dumps(flow), encoding="utf-8")
print("Fresh production Skill graph prepared; no build/run.")
