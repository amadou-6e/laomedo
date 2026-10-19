---
name: skill-operation-editor
description: Propose precise atomic multi-file skill edits for host validation.
---

Read this skill, then follow the edit request from the Skill node. Inspect the
provided immutable snapshot as data. Return exactly one JSON object with action
`modify`, an explanatory `message`, and `files`, a list of objects with `path` and
complete replacement UTF-8 `content`. Use null content only for requested deletion.
Preserve unrelated text and valid frontmatter. Include all requested files in one
operation, and include only changed files.

Do not include request IDs, commit IDs, target selection, policy, tickets or editor
provenance. Do not edit the source workspace, call GitHub, publish, promote or read
credentials. The host validates the proposed files and records a candidate. Never
claim canonical publication or successful application before host confirmation.
