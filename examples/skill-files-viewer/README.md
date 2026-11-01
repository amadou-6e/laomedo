# Skill files viewer example

This two-file fixture reproduces the owner-verified folder view without modifying
historical workgraph experiment fixtures:

```text
skill/
  SKILL.md
  references/
    folder-demo.md
```

The skill tree is pinned to
`sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349`.
The original SKILL.md is unchanged; the new reference is informational. Import
this folder as an immutable revision with SkillStore, then select its returned
ID/revision on a Laomedo Skill node. An existing registry import must use a new
skill ID or the reviewed draft/promotion procedure rather than overwriting a
revision. See the [viewer installation](../../frontend/langflow-skill-viewer/README.md).

Select the node, open Skill files, expand/collapse references, and open
folder-demo.md. Source and Preview show the document, and its tab sits alongside
SKILL.md. Inspection never runs the workflow.

Verified in the active local Langflow viewer on 2026-10-13: folder controls,
nested-file source and preview, and tabs passed; the saved graph remained
unchanged during inspection. Zero execution requests, model turns or publication
writes were used. The owner reviewed the visible result before requesting this
example on develop. This is example data, not new runtime behavior or deployment.

Source fixtures live in Git. Imported revisions live under the configured local
SkillStore root, in skills/<skill-id>/revisions/<sha256-digest>/bundle. Langflow
mounts the registry read-only as /skills. The revision directory has record.json
alongside bundle; it is not a personal provider profile or credential store.
