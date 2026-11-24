"""Check real installed template fidelity with zero model or server submissions."""

import json
from pathlib import Path
import sys

ROOT = Path("C:/CodeWorkspace/laomedo/.tools/worktrees/assistant-mcp-311")
sys.path.insert(0, str(ROOT / "src"))

from lfx.custom.utils import create_component_template
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog

paths = {
    "LaomedoCodexAgent": ROOT / "components/laomedo/codex_agent.py",
    "LaomedoClaudeAgent": ROOT / "components/laomedo/claude_agent.py",
    "LaomedoOpenCodeAgent": ROOT / "components/laomedo/opencode_agent.py",
    "LaomedoSkill": ROOT / "components/laomedo/skill.py",
    "MCPTools": Path("C:/CodeWorkspace/laomedo/.venv/Lib/site-packages/lfx/components/models_and_agents/mcp_component.py"),
}
results = []
for name, path in paths.items():
    template, _ = create_component_template(
        component={"code": path.read_text(encoding="utf-8"), "output_types": []}
    )
    catalog = ComponentCatalog({"installed": {name: template}})
    identity = "installed/" + name
    assert catalog.audited_family(identity) == name, name
    results.append({"component": name, "audited": True,
                    "inputs": list(template["template"]),
                    "outputs": [output["name"] for output in catalog.template(identity)["outputs"]]})
print(json.dumps({"model_submissions": 0, "metadata": results}, indent=2))
