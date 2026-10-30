# Structured data ownership

This pass starts at `a9317f61ce0376ead778802d3fd394fa127fe8a2`. Its purpose is to
replace repeatedly assembled records with canonical, feature-owned Pydantic
objects, preserving existing JSON, hashes and error contracts. The audit covers
all tracked Python, including components, examples, tools and historical
experiments. Historical experiments and fixture data are not production models
or evidence that a live workflow works.

## Object and method nomenclature

Use the domain name followed by its role: `SkillRevision`, `FrozenSkillDraft`,
`SkillCommit`, `AgentRunReference`, `PreparedRunRecord`, `GitHubIssue` and
`GitHubPullRequest`. A reference identifies retained state; a record describes
that state; a proposal describes an unperformed change. None grants permission.
Use `Base` only for an abstract interface. Canonical objects live in the owning
feature's `models.py`; public adapters import them directly.

`from_*` admits or projects an existing source, `to_*` serializes for an explicit
boundary. A model owns defaults, related fields and derived values. Stateful
services keep filesystem, HTTP, authorization and transaction effects. Existing
manual input checks retain their stable errors before constructing strict models.
Mutable external dictionaries are produced only at compatibility boundaries; this
pass does not claim every legacy provider lifecycle mutation is typed.

## Implemented value boundaries

| Concern | Owner | Objects and interface |
| --- | --- | --- |
| Initial Agent state | `agents/agents/base` | `PreparedRunRecord`; construct from admitted request/workspace/runtime binding, then `to_record()` for existing run persistence |
| Safe graph output | `agents/interface` | `AgentRunReference`, `PrecheckEvidence`; `from_result()` normalizes incomplete evidence, `to_payload()` preserves the graph contract |
| Agent coordination | `agents/orchestration` | `AgentHandoff` and its source/target/prior; construction after existing admission, `to_payload()` for the runner bridge |
| Skill registry | `skills/registry` | `SkillRevision`, `SkillDraft`, `FrozenSkillDraft` and nested hash/policy/validation records; byte identity and promotion stay with `SkillStore` |
| Skill edit journal | `skills/operations` | `SkillCommit` and result records; preserve optional-key omission and canonical hash preimages; transaction effects stay with `SkillOperations` |
| Normalized GitHub state | `github/issues`, `github/pull_requests` | `GitHubIssue`, `GitHubPullRequest`, `PullRequestHead`; explicit projections after existing response checks, no authorization inferred from identity |
| Other native and host records | their current owning features | Review each large dictionary; model fixed records, retain dynamic keyed maps and existing typed serializers |

Host value owners now include `OAuthAuthorizationRequest`, `OAuthAttempt`,
`OAuthCodeExchange` and `OAuthAccount` under credentials; `LeaseGrant`,
`GrantWindow`, `LeaseClock` and revocation/refusal records under leases;
`MediationServiceRecord` and `AuthorizedLeaseScope` under mediation; and initial
bundle/publication/verified identity records under publication. `WorkSnapshot`,
`RelevantWorkContent`, `WorkLaunchBinding` and local grant/result records keep
work selection and authorization evidence grouped without changing authority.
Provider attempt/token/telemetry/runtime values remain with their Agent owners.

The [complete large-block audit](structured-data-audit.md) records 47 migrated
or reused production constructors and the reasons for retaining 37 dynamic,
native-observation or existing model projections. It also covers nonproduction
Python and the JavaScript/TypeScript inventory. These are explicit scope decisions,
not a claim that every native event or historical lifecycle dictionary is typed.

Sensitive model fields use `SecretStr`, are excluded from ordinary dumps and
representations, and are unwrapped only by a deliberately named private-boundary
projection. Externally supplied configuration belongs to a Pydantic settings
object in `settings.py`. Static dispatch tables, error catalogues, JSON Schema
properties and file-path/hash maps remain mappings.

## Compatibility and validation

Compare exact payloads, absent versus null fields, canonical hash preimages,
unknown evidence, malformed input errors and credential redaction. Keep imports
and packaged resources working from an installed wheel. Internal tests support
these claims; changed runner behavior needs fresh real integration evidence.
Review and user acceptance of an earlier revision do not cover this increment.

The production mailbox relay remains a separate follow-up to ACP, tracked in
issue #215. Its assessment must cover authorization, sandbox networking, request
and response file safety, lifecycle, cancellation, cleanup and ambiguous writes
before experimental transport can be promoted.
