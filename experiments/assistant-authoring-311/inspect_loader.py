"""Compare the real directory loader for only the five owner-authorized adapters."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path("C:/CodeWorkspace/laomedo/.tools/worktrees/assistant-mcp-311")
sys.path.insert(0, str(ROOT / "src"))

from lfx.custom.directory_reader.directory_reader import DirectoryReader
from lfx.custom.directory_reader.utils import build_valid_menu
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from lfx.interface.components import _decorate_template_with_extension

paths = [
    ROOT / "components/laomedo" / name
    for name in ("codex_agent.py", "claude_agent.py", "opencode_agent.py", "skill.py")
]
paths.append(Path("C:/CodeWorkspace/laomedo/.venv/Lib/site-packages/lfx/components/models_and_agents/mcp_component.py"))
reader = DirectoryReader(str(ROOT / "components"), compress_code_field=False)
menu = reader.build_component_menu_list([str(path) for path in paths])
snapshot = build_valid_menu(reader.filter_loaded_components(menu, with_errors=False))
catalog = ComponentCatalog(snapshot)
for category, components in snapshot.items():
    for name, metadata in components.items():
        code = metadata["template"]["code"]["value"]
        print(json.dumps({
            "identity": category + "/" + name,
            "source_hash": hashlib.sha256(code.replace("\r\n", "\n").strip().encode()).hexdigest(),
            "audited_family": catalog.audited_family(category + "/" + name),
        }))
        namespaced = "ext:" + category + ":" + name + "@extra"
        decorated = _decorate_template_with_extension(
            metadata,
            extension_id=category,
            bundle=category,
            extension_version="0.0.0",
            namespaced_id=namespaced,
            legacy_name=name,
        )
        actual = ComponentCatalog({category: {namespaced: decorated}})
        assert actual.audited_family(category + "/" + namespaced) == name
        print(json.dumps({"namespaced_identity": category + "/" + namespaced, "audited": True}))
