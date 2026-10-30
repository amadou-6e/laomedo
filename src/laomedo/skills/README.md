# Skill ownership

Skills owns source discovery and pinning, immutable registry content, authorized
multi-file edits, commit-style history and read-only inspection. A byte revision
is distinct from a commit identity. Editing does not promote canonical latest
or publish Git commits. Existing Pydantic models remain the canonical records.

## Current checkpoint

C1 extracts module-level HTTP handlers for the existing source and operation
servers and moves their identical redirect refusal to neutral
`laomedo.http.redirect.NoRedirect`. Core Skills must not depend on host, Agents,
GitHub, work_graph or an optional graph framework. No endpoint or service command
is relocated. Real source/edit/history graph acceptance remains a separate gate.

| Concern | Owner | Object/function vocabulary |
| --- | --- | --- |
| Immutable content and drafts | `registry/` | `SkillStore`; import_skill, revision, read_file, create_draft, freeze_draft, promote_draft |
| Source discovery and immutable choices | `sources/` | `SkillSources`; discover, revisions, resolve |
| Atomic edits and journal queries | `operations/` | `SkillOperations`; prepare, apply, history, diff, compare |
| Read-only byte verification | `inspection/` | `inspect_skill`; no mutable-store construction |
| Description authoring contract | `authoring/` | has_description, summary_authoring; never execute skill content |
| Current loopback HTTP boundary | `sources/`, `operations/` | `*Server` owns lifetime/state; module-level `*RequestHandler` owns protocol handling |

Use responsibility nouns such as Store, Server and RequestHandler; reserve Base
for a real abstract contract and Ledger for append-only facts. Independent
functions stay function-only. Do not split SkillOperations' atomic transaction
into an artificial second ledger merely to shorten a file.

The later reviewed `interface/` target means actual public contracts and adapters
used by the app, as in Agents. Adapter relocation is C3. The misplaced generic
publication ingress, Agent-only workspace helpers and source Git launcher are
recorded redesign work; C1 does not claim they are fixed.
