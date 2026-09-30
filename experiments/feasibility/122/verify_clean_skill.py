"""Verify only the synthetic edited SKILL.md, excluding runtime artifacts."""

from pathlib import Path
import json
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_codex_edit import validate_draft
from probe_draft_guards import inventory, tree_hash


run = Path(sys.argv[1]).resolve(strict=True)
canonical = run / "canonical-skill"
source_draft = run / "draft-workspace" / "SKILL.md"
with tempfile.TemporaryDirectory(prefix="laomedo-clean-draft-") as scratch:
    draft = Path(scratch)
    shutil.copy2(source_draft, draft / "SKILL.md")
    result = validate_draft(canonical, draft, tree_hash(inventory(canonical)))
    print(json.dumps({
        "changed_paths": result["changed_paths"],
        "violations": result["violations"],
        "base_evaluation_passed": result["base_evaluation"]["passed"],
        "draft_evaluation_passed": result["draft_evaluation"]["passed"],
        "patch_present": bool(result["patch"]),
    }, indent=2))
