# Skills

Skills owns source discovery and pinning, immutable registry bytes, authorized
multi-file edits, commit-style history and read-only inspection. A byte revision
is distinct from a journal commit: returning to earlier bytes can still produce
a later edit-history commit. Editing does not promote canonical latest or publish
Git commits. Explicit registry promotion and later Git publication remain separate.

## Concerns and defining interfaces

| Concern | Owner | Object or function vocabulary |
| --- | --- | --- |
| App-facing loopback HTTP | `interface/sources/`, `interface/operations/` | Source/operation clients, servers, module-level request handlers, Settings and trusted CLI startup |
| Source discovery and immutable choices | [sources/](sources/README.md) | `SkillSources`: discover, revisions, resolve; concrete LocalSkillSource and GitSkillSource retain admission/read policy |
| Immutable bundles and drafts | [registry/](registry/README.md) | `SkillStore`: import_skill, revision, read_file, create_draft, draft_workspace, freeze_draft, promote_draft |
| Atomic edits and history | [operations/](operations/README.md) | `SkillOperations`: prepare, apply, history, diff, compare; one authorization/replay/journal transaction |
| Read-only verification | `inspection/` | `inspect_skill`; verify exact immutable bytes without constructing a mutable store |
| Description authoring contract | `authoring/` | has_description, summary_authoring; load the packaged instructions without executing skill content |

The interface directories contain the actual public adapters, not forwarding
facades. Core domain services/models do not import an optional graph framework.
Only explicit CLI startup composes and starts services. HTTP routes, credentials,
wire limits and unknown-outcome rules stay with those adapters.

## Object and method nomenclature

Store owns immutable/draft persistence. Reference binds an admitted identity;
Revision identifies immutable byte metadata; Draft names an independent editable
copy. SkillProposal and FileEdit describe candidate edits, not authority.
SkillCommit records the edit history; SkillComparison describes a historical
snapshot compared to the viewer's pinned current revision. Their canonical
Pydantic definitions live in each feature's models.py. Explicit projections retain
wire/persisted shapes and do not impose a new schema on historical readers.

Use Source for an admitted read capability, Server for endpoint lifetime/state,
and RequestHandler for protocol handling. Base is reserved for a real abstract
responsibility. SkillOperations already binds authorization, replay, filesystem
staging and commit history atomically; it needs no artificial second Ledger.
Independent functions have focused function-only owners, and callers import
defining symbols directly. Leaf READMEs explain the public method vocabulary.

## Boundaries

GitSkillSource retains source admission and cache accounting while composing the
single generic GitCommandRunner in laomedo/git. HTTPS source reads do not inherit
host credentials, interactive prompts or redirects. No parallel source Popen
launcher is retained. Registry helpers own path/byte/policy/diff mechanics; they
do not acquire Agent, host publication or GitHub responsibilities.

Agent-only delivery and working-state helpers belong under
[agents/workspaces](../agents/workspaces/README.md). Their relocation is proposed
in this README-first checkpoint; no compatibility workspace namespace is intended
under general Skills. Generic run-bound bundle ingress belongs to
host/publication/ingestion and does not inspect or modify skills. The dependency
direction is callers into Skills; core Skills does not depend on Agents, host,
GitHub, work_graph or a graph framework.

Structural/protocol checks, CI and review support this boundary. Real source
selection/pinning, multi-file editing, history/diff browsing, errors/recovery and
requesting-user validation remain separate browser/graph acceptance gates.
