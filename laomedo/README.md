# Local skill revision and draft core

`skill_store.py` is the first deterministic implementation of the Laomedo
Skill Revision and Skill Draft contracts. It requires Python 3.10+ and only
the standard library. It provides immutable, content-addressed skill
revisions; exact file hashes and reads; independently hashed editing policies;
reviewable draft workspaces and diffs; and a separate promotion operation that
requires the reviewed draft hash and an unchanged base revision.

```python
from pathlib import Path
from laomedo.skill_store import SkillStore

store = SkillStore(Path(r"C:\private\laomedo-store"))  # outside Git
base = store.import_skill("my-skill", Path("source-skill"))
policy = {
    "policy_id": "my-skill-edit-rules", "revision_id": "1",
    "allowed_paths": ["SKILL.md"], "allowed_suffixes": [".md"],
    "allow_new_files": False, "allow_scripts": False,
    "allow_dependencies": False, "allow_assets": False,
    "required_frontmatter": ["name", "description"],
    "permitted_validation_commands": ["structural-v1"],
    "max_files": 1, "max_file_bytes": 8192,
}
draft = store.create_draft("my-skill", base["revision_id"], policy)
workspace = store.draft_workspace(draft["draft_id"])
# A human edits workspace / "SKILL.md" and reviews the resulting diff.
result = store.freeze_draft(draft["draft_id"])
if result["promotion_eligible"]:
    reviewed_hash = result["proposed_tree_hash"]
    # After explicit human review, call promote_draft separately.
    store.promote_draft(draft["draft_id"],
                        expected_base_revision=base["revision_id"],
                        reviewed_draft_hash=reviewed_hash)
```

The store detects links, Windows junctions, special files, tampered revision
bytes, policy changes, forbidden draft paths, and stale base revisions. It
revalidates frozen bytes at promotion. The original imported source and past
revisions remain untouched. Its locks fail closed after an interrupted writer;
recovery and retention policy are future work.

This is **not** an OS sandbox or a multi-user service. An untrusted agent must
run under an independently enforced write boundary, and the store must only
freeze its output after that process ends. The #122 spike did not yet produce
a successful agent edit. Rule/example item manifests and selected-subset
materialization remain separate work; `read_file` returns exact revision bytes
and provenance but does not claim that an agent consumed them.

Run the core tests from the repository root:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```
