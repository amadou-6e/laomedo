# Agent provider parity plan

Status: proposed; awaiting Claude review before implementation. This document
does not establish runtime acceptance or authorize a merge.

Owner: issue #205 / draft PR #250. Baseline: `refactor/205` at `19c7f1f`.
Reuse the assembled implementation and its provenance; do not create a parallel
provider architecture. Reconcile the plan with the current develop head and
ACP dependency PRs before selecting implementation commits.

## Goal and acceptance boundary

The wider application must use one Agent contract regardless of provider.
Fresh, Resume, status, cancel, discovery, readiness, runtime identity, output
validation, activity and cleanup must have explicit, consistent meanings.
Native differences remain behind provider-owned adapters. Equal folder or file
counts are not a requirement; equal responsibility boundaries are.

An unsupported capability must be reported before dispatch, not discovered
through a missing factory or private constructor knowledge. Explicit capability
reporting is an intermediate improvement, not completion of a missing feature.
In particular, OpenCode deployment and output validation remain open work until
their acceptance paths pass.

Preserve existing public payloads, stable error codes, saved-run identities and
persisted schemas. Any necessary external extension needs an explicit versioned
contract/spec change and compatibility checks. Never silently migrate saved runs
to a new image, credential binding, policy or execution mode.

## Verified gaps and retained native differences

The baseline column records the starting architecture, not an assertion that
retired objects still exist. Issue #275 delivers explicit runtime, command,
credential, discovery and Activity roles, with host-owned registration; see the
[implemented contracts](../../src/laomedo/agents/agents/README.md#provider-role-contracts-275).
Provider deployment parity and whole-pipeline lifecycle consolidation remain
separate work. New fixture/structural coverage does not establish live parity.

| Area | Baseline | Required outcome |
| --- | --- | --- |
| Docker packaging | OpenCode's recipe was archived at `dbc528af`; no maintained replacement. Codex folder names the protocol, Claude names the provider. | Provider-owned `docker/{codex,claude,opencode}` builds; checked versions and immutable runtime identity. |
| Deployment | OpenCode requires an injected transport and has no maintained CLI. | All providers construct through supported configuration and expose the same host API. |
| Runtime interface | Codex `controller/`, Claude `container.py`, OpenCode `boundary.py` spread similar responsibilities differently. | A narrow runtime contract and discoverable provider-owned implementations. |
| Lifecycle | Shared ACP transport exists, but providers retain substantial whole-pipeline overrides. | One owner for shared sequencing and finalization, with bounded native hooks. |
| Readiness | OpenCode reports transport configuration, unlike active sibling checks. | Separate configuration, Docker/image, authentication, protocol and isolation observations; no configured-equals-ready claim. |
| Identity | OpenCode's initial binding omits image/profile values. | Validate and retain the admitted runtime binding before model dispatch. |
| Output | OpenCode rejects output requirements. | Shared final-response validation for every provider; native precheck is an additional advertised capability. |
| Activity | Codex/native result parsing remains partly in common Activity. | Provider-native decoding, shared normalized storage/aggregation/presentation. |
| Command workers | OpenCode pins the Codex ACP image; similar worker lifecycle exists in several adapters. | Explicit shared worker ownership and reused mechanics, preserving distinct native wire adapters. |
| Discovery | Claude has a separate static effort allowlist module. | Discover choices natively; separate genuine protocol constraints from model capabilities. |
| Documentation/tests | Uneven provider documentation and mostly separate lifecycle controls. | Common contract coverage plus native tests, current docs and real acceptance evidence. |

Keep Codex's adapter extension, executor registration and seccomp resources;
Claude's access-only writer and native OTLP receiver; OpenCode's native history
reader and MCP codec. Do not reproduce these in siblings for visual symmetry.
Host sign-in, secure storage, authorization and GitHub mediation stay with their
current domain owners. No expansion of mediation scope is included.

## Target ownership and object nomenclature

Write/update the owning module README before moving implementation. Define the
object names and method/effect contracts there, including cancellation, closure
and uncertain outcomes. Leaf object packages document their methods as well.

```text
agents/
  interface/                    # Stable application-facing contract
    models.py                   # Extend canonical values; no duplicate run model
    output/                     # Shared response validation
    langflow/                   # Agent graph integration
  agents/
    base/
      agent.py                  # BaseAgent: shared host lifecycle
      runtime.py                # BaseAgentRuntime: abstract native runtime contract
      models.py                 # Canonical internal runtime values
      acp/                      # Existing shared ACP session/transport
    {codex,claude,opencode}/
      README.md
      agent.py                  # CodexAgent / ClaudeAgent / OpenCodeAgent
      cli.py                    # Provider entrypoint using shared host CLI plumbing
      settings.py
      runtime/
        README.md
        runtime.py              # CodexAgentRuntime / ClaudeAgentRuntime / OpenCodeAgentRuntime
        ...                     # Only actual native launch/execution requirements
      activity/
        ...                     # Native decoding and evidence acquisition
      auth/                     # Only where native credential adaptation is needed
      models.py                 # Only where canonical provider values are needed
  activity/                     # Normalized storage, aggregation and presentation
docker/
  codex/
  claude/
  opencode/
  worker/                       # Only after extracting a proven common worker image
```

`Base` identifies an abstract extension contract; provider names identify concrete
implementations. Proposed runtime verbs are `open`, `prompt`, `cancel`,
`collect_evidence` and `close`: `open` creates or loads an explicitly bound native
session; `prompt` submits one turn; `cancel` requests interruption; evidence and
closure return observed outcomes rather than implying success. Discovery and
readiness remain separate operations that spend no model turn. Confirm exact
signatures against all three existing implementations during review.

The runtime interface is internal. The application continues through
`agents/interface`; it must not import concrete runtime modules. Credential
contents never enter capability, readiness or identity models. New related values
use canonical Pydantic models in the owning `models.py`, with explicit boundary
projections. Externally provided settings use feature-owned Pydantic settings.
Implementation files contain classes or standalone functions, never both.

## Delivery sequence

### 1. Freeze the contract and baseline

- Inventory all application/host callers and capability differences. Document
  the current method signatures, payloads, terminal states, readiness semantics,
  identity fields and unsupported behavior before changing them.
- Define the minimum supported-provider contract and separately advertised
  capabilities, including native precheck, child evidence and mediated actions.
  Unknown evidence is distinct from unsupported capability and failed execution.
- Record production Python/MJS/TS lines, test lines, file counts and duplication
  at the baseline, excluding locks, vendored code, generated files and archives.
  Track these separately after every block; do not conceal transferred code.
- Prepare the spec changes and common contract cases first. Preserve old-schema
  reading and explicit binding-mismatch behavior.

Exit: Claude approves the contract, target ownership and migration order before
implementation. No new universal plugin registry or configuration framework.

### 2. Repair deployment and package ownership

- Recover the exact archived OpenCode Docker recipe as provenance, then validate
  the dependencies required by its current ACP launch; do not treat restoration
  alone as a working deployment.
- Use `docker/codex`, `docker/claude`, `docker/opencode`; update build commands,
  CI, resource paths and documentation together. Preserve existing image tags
  and saved-run bindings unless an intentional reviewed image change is required.
- Add the supported OpenCode construction/configuration/CLI path. Reuse shared
  host argument plumbing rather than copying either sibling's complete CLI.
- Validate selected image/CLI/protocol and derive safe identity before dispatch.
  Missing image, login, Docker or transport must yield descriptive catalogue errors.

Exit: all providers can be configured, discovered and checked without model work;
fresh-machine build instructions do not depend on private harnesses or `exp`.

### 3. Align native runtimes and command execution

- Move equivalent runtime ownership into provider `runtime/` packages and adapt
  the existing implementations to `BaseAgentRuntime`. Remove replaced modules
  and migrate callers in the same change; no forwarding facades or empty packages.
- Preserve their actual lifetime policies: Claude's per-turn scope and the other
  adapters' attempt/session scopes must not be homogenized without evidence.
- Keep Codex ACP extensions, Claude's bridge and OpenCode MCP as narrow codecs.
  Share command admission/execution/receipt handling only where their guarantees
  match. Generic Docker operations remain in py-docker.
- Verify the common worker requirements before introducing `docker/worker` and
  removing OpenCode's Codex-image dependency. Give the worker its own immutable
  binding and documented credential/network/mount policy.

Exit: runtime ownership and method contracts match; exact resource cleanup and
native isolation remain enforced. Codex split isolation requires native-path
evidence; direct Docker probes cannot close that existing gap.

### 4. Consolidate lifecycle and capability behavior

- Extract one shared lifecycle step at a time: admission/binding, session open,
  dispatch, cancellation, terminal interpretation, evidence, freeze and closure.
  Keep provider-specific terminal interpretation inside its adapter.
- Remove each superseded provider block in the same PR. Retain first-failure
  precedence, durable request identity, post-dispatch uncertainty and no blind retry.
- Make readiness observations comparable without confusing configured transport
  with authentication, isolation or operational readiness. Map legacy payloads
  explicitly if the public presentation is extended.
- Supply shared final-output validation for OpenCode. Define bounded correction
  behavior explicitly; if correction is unsafe/unsupported, report validation
  failure without hidden resubmission. Keep native precheck optional and distinct.
- Validate native model/effort metadata without manufacturing support from static
  lists. Keep fixed wire/security constraints in settings, not a fake catalogue.

Exit: the same caller can execute each supported provider without private
construction knowledge or provider-specific success/uncertainty handling.

### 5. Finish Activity ownership and documentation

- Move Codex and other native parsing out of common Activity. Keep only canonical
  records, aggregation and presentation there. Place OpenCode native history under
  its Activity owner if its complete caller inventory confirms that ownership.
- Preserve native raw evidence, parent/child identity, unknown usage and explicit
  capture completeness; separate task completion from evidence/cleanup outcomes.
- Document every remaining structural difference and native capability. Update
  stale HTTP/SSE descriptions to the actual ACP path without rewriting historical
  evidence as current verification.
- Keep the one maintained example builder, with caller-selected real inputs.
  Experimental probes/evidence stay on `exp`; tests never fetch that branch.

Exit: every provider-specific folder has a documented reason; no common module
interprets a native provider payload or imports a concrete runtime.

### 6. Validate and review the complete result

- Parameterize common lifecycle contract cases across provider implementations;
  retain native-specific tests. Test folders use `test_*`; reusable setup belongs
  beside its concern. Controlled traffic is internal regression evidence only.
- Run source/package/import, resource, structural and Black/CI checks. Confirm
  installed-wheel origin before relying on installed tests.
- For each provider, verify real Fresh and Resume on one identity, cancellation,
  restart recovery, model discovery, output validation, activity and exact cleanup.
  Cover unavailable Docker, missing image, expired authentication, protocol/binding
  mismatch, lost dispatch response and cleanup uncertainty without unsafe replay.
- Exercise the maintained graph and shared error UI in the actual browser. Record
  revision, environment, stories, evidence and unresolved gaps. Use an existing
  approved integration task; do not invent a README audit or export workspace files.
  If no suitable real path is authorized/available, leave it explicitly unverified.
- Obtain Claude's full substantive review and focused rechecks for findings.
  Request the owner's final graph inspection/validation before any merge.

Exit: no claimed capability lacks its required evidence; all merge gates pass.

## Size and checkpoint gates

Commit and push each coherent block promptly with pending checks stated. Keep
review units independently understandable and based on the owning issue branch;
do not add another long stack of unchecked refactor branches. The reviewer should
confirm the production cut boundaries before any split into additional PRs.

The consolidation target is production-source parity or reduction against this
baseline. Necessary new capability code and tests are reported separately.
If production size grows, identify the exact files and explain retained/new/deleted
logic, then reinvestigate or notify the owner before proceeding. Do not remove
failure/security coverage to achieve a line-count target.

## Questions for Claude

1. Does the minimum application contract close the actual gaps, rather than only
   advertise missing capabilities?
2. Is the runtime boundary small enough to reduce duplicated lifecycle logic while
   preserving provider lifetimes and native completion/cleanup guarantees?
3. Which command-service blocks are genuinely equivalent, and which must remain
   native wire/policy adapters? Is a neutral worker image sufficient?
4. Are binding compatibility, output correction, raw evidence, native sandbox
   isolation and authentication ownership fully covered?
5. Can the sequence be simplified further without a second architecture, wrapper
   sprawl or an increase hidden by moving code between packages?

No Claude verdict has been requested or obtained for this plan yet.
