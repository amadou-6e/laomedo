# Skill ownership

Skills owns source discovery and pinning, immutable registry content, authorized
multi-file edits, commit-style history and read-only inspection. A byte revision
is distinct from a commit identity. Editing does not promote canonical latest
or publish Git commits. Existing Pydantic models remain the canonical records.

## Earlier handler checkpoint

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
| Public loopback HTTP boundary | `interface/sources/`, `interface/operations/` | `*Server` owns lifetime/state; module-level `*RequestHandler` owns protocol handling |

Use responsibility nouns such as Store, Server and RequestHandler; reserve Base
for a real abstract contract and Ledger for append-only facts. Independent
functions stay function-only. Do not split SkillOperations' atomic transaction
into an artificial second ledger merely to shorten a file.

The `interface/` boundary contains the actual public adapters used by the app,
as in Agents. Agent-only workspace helpers and the source Git launcher remain
later redesign work; this adapter move does not claim they are fixed.

C2 moves generic run-bound bundle ingress to `host/publication/ingestion/`.
It does not inspect or modify skills and therefore has no compatibility owner
under this package. Registry, source and operation behavior remain unchanged;
Agent-only workspace helpers and source Git launcher changes are later work.


## C3 public interface design

The `interface/` boundary contains the existing HTTP adapters:
clients, handlers, servers, feature-local Settings and trusted startup CLIs.
Its README and per-feature READMEs define the object/method vocabulary before
implementation. Domain models, gateways/services and immutable persistence remain
under their existing owners; no common handler base or forwarding layer is added.
Application callers use defining modules in interface; only explicit CLI startup
loads host/native composition. Source-domain fixed policy remains source-owned.
Current checkpoint status and migration constraints are in `interface/README.md`.


## Registry helper ownership

The registry README defines the Store/reference/revision/draft vocabulary and
method contract before its D1 split. Path admission, exact hashing, filesystem
record I/O, policy checks and patch rendering have separate function-only owners
under `registry/`; no service or model facade is introduced. Existing canonical
Pydantic records and atomic SkillOperations transactions remain intact. Source
Git behavior and Agent workspace ownership are separate later checkpoints.
