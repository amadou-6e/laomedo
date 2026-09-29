# Local skill revision and draft core

`skill_store.py` is the first deterministic implementation of the Laomedo
Skill Revision and Skill Draft contracts. It requires Python 3.10+ and only
the standard library. It provides immutable, content-addressed skill
revisions; exact file hashes and reads; independently hashed editing policies;
reviewable draft workspaces and byte-exact diffs; and a separate promotion
operation that requires the reviewed draft and policy hashes plus an unchanged
base revision. Draft workspaces default to a sibling directory of the store,
so a later runner can grant write access to one workspace without granting
write access to revision, policy, or review records.

```python
from pathlib import Path
from laomedo.skill_store import SkillStore

store = SkillStore(Path(r"C:\private\laomedo-store"))  # outside Git
base = store.import_skill("my-skill", Path("source-skill"))
policy = {
    "policy_id": "my-skill-edit-rules", "revision_id": "1",
    "allowed_paths": ["SKILL.md"], "allowed_suffixes": [".md"],
    "allow_new_files": False, "allow_deletions": False,
    "allow_scripts": False,
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
                        reviewed_draft_hash=reviewed_hash,
                        expected_policy_hash=result["policy_ref"]["hash"])
```

The store detects links, Windows junctions through `os.lstat` on supported
Windows Python versions, hardlinks, special files, tampered revision bytes,
policy changes, forbidden draft paths, and stale base revisions. It rejects
changed non-UTF-8 files until a binary review path exists. The patch escapes
line endings and other nonprinting characters, so a CRLF-only change is
visible. Invalid drafts remain in their workspace as evidence and are never
copied into a promotable frozen bundle. Promotion revalidates frozen bytes and
records each transition separately from the content-addressed revision; this
also records a revert to an older revision. Matching interrupted freezes can
be retried, and a retry can repair promotion bookkeeping after the latest
pointer was written. Conflicting partial freezes and stale locks fail closed;
automatic recovery and retention policy are future work.

This is **not** an OS sandbox or a multi-user service. Path and hardlink
checks occur after filesystem changes, so they cannot prevent a process with
write access to the canonical files from damaging them. An untrusted agent
needs an independently enforced write boundary for only its draft workspace,
with the store protected from its OS identity. Freeze only after that process
ends. The #122 spike did not yet produce
a successful agent edit. Rule/example item manifests and selected-subset
materialization remain separate work; `read_file` returns exact revision bytes
and provenance but does not claim that an agent consumed them.

Run the core tests from the repository root:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```
