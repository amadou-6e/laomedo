# Agent architecture redesign

**Status: PROPOSED, NOT IMPLEMENTED.** This document records the target design
discussed with the owner. It is not a description of the current folder layout,
a completed refactor, or approval to merge. Claude reviewed the design direction;
the implementation contracts and migration still require the checks below.

The goal is to make providers visible entrypoints, give each concern an owning
object, and inherit the common execution lifecycle through `BaseAgent`. Matching
folders must reflect shared behavior rather than three independent pipelines.

For current product documentation, see the [Agents guide](../../../docs/features/agents/README.md).
Canonical requirements remain in the separate specs repository.

## Concerns and owning objects

Paths in this table are relative to `src/laomedo/` and describe the target.

| Concern | Folder | Objects and responsibility |
| --- | --- | --- |
| Public Agent API | `agents/interface/` | `HttpAgentBridge`, `AgentRequest`, `AgentCapabilities`: the boundary used by the rest of the app |
| Shared Agent behavior | `agents/base/` | `BaseAgent`, `AcpRuntime`, `AgentRegistry`: inherited lifecycle, communication and trusted registration |
| Concrete providers | `agents/codex/`, `agents/claude/`, `agents/opencode/` | `CodexAgent`, `ClaudeAgent`, `OpenCodeAgent`: provider behavior and resources |
| Working files | `workspaces/` | `BaseWorkspace`, `DirectoryWorkspace`, `GitWorkspace`: prepare, verify, snapshot and restore working state |
| Git repositories | Initially `workspaces/git/`; `repositories/git/` if shared use is established | `GitRepository`: controlled Git operations; caller-specific workspace admission and publication authorization stay with their callers |
| Transferable files | `artifacts/` | `ArtifactStore`, `ArtifactReference`: retain, select, verify and import output files |
| Execution persistence | `executions/` | `RunStore`, `RunRecord`, `RunReference`: reservations, state, correlation and recovery information |
| Expected output | `output/` | `OutputValidator`, `OutputRequirements`, `OutputValidation`: describe and check acceptable responses |
| Coordination between agents | `orchestration/` | `BoundedAgentController`, `AgentHandoff`: coordinate successive runs and explicit stopping conditions |
| Shared observability | `activity/` | `ActivityStore`, `ActivityCapture`, `ActivityProjection`: retain and present normalized activity |
| Graph integration | `integrations/langflow/` | Components, feedback connections and downstream requirement discovery |

`Workspace` is a behavioral object, not a namespace for filesystem helpers.
`GitWorkspace` uses a `GitRepository` to prepare its working state. Git mechanics
may be shared by workspace preparation and verified publication. A caller audit
must establish the common operations and actual consumers before extracting
`repositories/git/`. Until then, `GitRepository` belongs in `workspaces/git/`.
Relocate it if extraction is justified; do not keep two implementations. GitHub
grants, remote selection and publication authorization stay with their callers.

## Target structure

```text
laomedo/
├── agents/
│   ├── claude/
│   ├── codex/
│   ├── opencode/
│   ├── interface/
│   │   ├── bridge.py          # HttpAgentBridge
│   │   ├── models.py          # Public Agent requests and descriptors
│   │   └── errors.py          # Public error exports
│   ├── base/
│   │   ├── agent.py           # BaseAgent
│   │   ├── runtime.py         # AcpRuntime
│   │   ├── registry.py        # AgentRegistry
│   │   ├── catalog.py         # Shared caching/discovery coordination
│   │   ├── models.py
│   │   ├── settings.py
│   │   ├── errors.py
│   │   └── acp/              # Shared protocol implementation
│   └── ADD_PROVIDER.md
├── workspaces/
│   ├── base.py               # BaseWorkspace
│   ├── directory.py          # DirectoryWorkspace
│   ├── git/
│   │   ├── workspace.py      # GitWorkspace
│   │   └── repository.py     # GitRepository until shared extraction is justified
│   └── models.py
├── repositories/             # Conditional on the shared Git caller audit
│   └── git/
│       ├── repository.py     # GitRepository relocated from workspaces/git/
│       └── models.py
├── artifacts/
│   ├── store.py              # ArtifactStore
│   └── models.py
├── executions/
│   ├── store.py              # RunStore
│   └── models.py
├── output/
│   ├── validator.py          # OutputValidator
│   └── models.py
├── orchestration/
│   ├── controller.py         # BoundedAgentController
│   └── models.py
├── activity/                 # Shared storage, capture and presentation
└── integrations/
    └── langflow/
        ├── agent/            # Existing public component entrypoint
        ├── feedback/         # PR/Skill and Agent graph loops
        └── output/           # Downstream requirements and graph routing
```

Settings, errors and package initializers are omitted from parts of this tree
for readability. Introduce them where the concern needs them. Do not create
empty files or duplicate models solely to make folder contents identical.
`ADD_PROVIDER.md` is a planned extension guide, not an existing runnable example.

## Provider ownership

Each provider has the same core responsibilities. Codex illustrates the layout:

```text
agents/codex/
├── agent.py                  # CodexAgent(BaseAgent)
├── launch.py                 # CodexLaunchPolicy
├── catalog.py                # CodexModelCatalog
├── models.py                 # Codex-specific structured values
├── settings.py
├── errors.py
├── authentication/           # Connection and credential binding
├── activity/                 # Native evidence interpretation
│   ├── projector.py          # CodexActivityProjector
│   ├── rollout.py
│   └── models.py
├── extensions/               # Actual provider-specific protocol policies
├── split/                    # Optional split-executor capability
├── resources/                # Required runtime assets
└── docker/                   # Build definitions, after context/package-data audit
```

Claude and OpenCode follow the same core roles. Additional packages represent
actual capabilities, such as `agents/opencode/activity/history/`.

Provider-specific authentication logic, catalogue discovery, native Activity
interpretation, runtime resources and policy extensions belong with the provider.
This supersedes the earlier proposed `activity/codex/` layout: generic Activity
code receives registered adapters and canonical records without provider-name
branches. Original native evidence remains separately retained with provenance.

Generic secure credential storage, leases and mediation remain shared host
services. General Docker mechanics remain in `py-docker`. Moving build recipes
requires a build-context, image and package-data audit; only assets needed by an
installed runtime belong in the wheel.

## Inheritance and composition

```text
CodexAgent ----+
ClaudeAgent --+-- inherit BaseAgent
OpenCodeAgent-+

BaseAgent uses:
  Workspace
  AcpRuntime
  RunStore
  ArtifactStore
  OutputValidator
  ActivityCapture
```

`BaseAgent` inherits the common lifecycle once for all providers and coordinates
the other objects by composition. It does not absorb Git commands, SQLite
operations, file copying or validation implementation into one large class.

Provider hooks cover authentication, launch policy, native model discovery,
session lifetime, cancellation confirmation and native evidence. The final hook
signatures require a source audit before lifecycle extraction. Providers must
eventually stop overriding whole execution pipelines.

Necessary differences must stay explicit:

| Phase | Codex | Claude | OpenCode |
| --- | --- | --- | --- |
| Resource lifetime | Controller and optional executor generally span an attempt and its corrections | Container opens and closes per turn | Controller/broker span an attempt; metadata jobs follow |
| Output correction | Continue the same native thread with effect and precheck guards | Resume the native session in a new turn scope, with correction tools disabled | Output requirements are currently unsupported |
| Cancellation | Native interruption and exact cleanup confirmation | Stop the exact turn resources and reconcile its lease | Stop the exact broker/controller and confirm cleanup |
| Evidence and snapshot | Confirm close before freezing; retain native extension evidence | Close turn resources and telemetry before the final snapshot | Confirm close, seal capture, export native history, then freeze |

The common invariant is that snapshots require confirmed workspace quiescence.
Native cancellation confirmation, resource cleanup, task outcome and evidence
completeness are distinct facts. A partial capture must not become a successful
capture merely because the agent finished, and uncertainty must not trigger a
blind redispatch.

## Public boundary and registration

- Application consumers use `agents/interface`; they do not import concrete
  providers or the base implementation. Explicit host bootstrap and runner-server
  wiring are the exceptions: they register trusted factories and delegate to the
  base. Import-boundary checks must identify those entrypoints explicitly.
- The interface imports domain models, not base or provider implementations.
  It re-exports canonical models from their owning concern where necessary.
- The base depends on those public data contracts and shared domain objects.
  Concrete providers depend on the base.
- Host startup selects explicit trusted provider factories. The registry does
  not automatically execute factories advertised by installed packages.
- A graph selects a configured provider ID. It cannot supply import paths,
  commands or credential locations.
- Preserve the existing error hierarchy and stable machine codes. A naming
  migration must not create a parallel hierarchy or lose catalogue coverage.

Moving the HTTP client into `HttpAgentBridge` must preserve request/run identity,
Stop behavior, token handling and the existing wire schemas. Update producer-path
coverage guards and add import-boundary checks with that migration.

## Object nomenclature

Use `Base` for abstract classes, meaningful qualifiers where there are actual
variants, and a final noun describing the responsibility.

| Name | Meaning |
| --- | --- |
| `BaseAgent`, `BaseWorkspace` | Abstract classes with defined extension contracts |
| `CodexAgent`, `GitWorkspace` | Concrete specializations |
| `AcpRuntime` | Execution machinery communicating through ACP |
| `HttpAgentBridge` | Connector across the application/runner boundary |
| `ArtifactStore`, `RunStore` | Persistence and retrieval of entities |
| `BoundedAgentController` | Coordination with explicit execution bounds |
| `CodexActivityProjector` | Conversion of native evidence to the common Activity model |

Reserve `Ledger` for ordered, append-only facts. The current mutable execution
persistence should be named `RunStore`. Use `Full`, `Async` or `Sync` only when
they distinguish precisely defined supported variants. This proposal does not
introduce an async-core conversion or parallel sync/async execution pipelines.

Keep one canonical Pydantic model per structured concept in its owning
`models.py`, with described fields. Put externally supplied configuration in
Pydantic settings objects in `settings.py`. Keep behavioral methods with their
owning objects and standalone functions in focused function-only modules.

## Adding a provider

The extension guide and shared conformance suite must make these steps explicit:

1. Create the provider package directly under `agents/`.
2. Subclass `BaseAgent` and implement the documented provider hooks.
3. Supply native catalogue discovery, authentication integration, launch policy,
   Activity interpretation, capabilities, resources and descriptive errors.
4. Register its factory through explicit trusted host configuration.
5. Pass shared conformance checks and real user-path checks for supported
   Fresh, Resume, Stop, failure, cleanup and Activity stories.

Unsupported capabilities must be explicit. Missing native usage stays unknown.
Fixture tests do not establish real provider acceptance. A provider fitting the
existing contract should not require edits to another provider or provider-name
branches in shared code; a genuinely new capability may require an explicit
contract extension.

## Migration and acceptance

Separate the work into reviewable replacements:

1. **Relocate and name existing behavior.** Initially `BaseAgent` is the current
   shared Runner renamed and relocated, with existing provider overrides retained.
   This step alone does not complete lifecycle consolidation.
2. **Establish canonical Activity adapters.** Define shared records and trusted
   adapter registration before relocating native parsers. Check each provider's
   actual Activity and original evidence.
3. **Consolidate execution provider by provider.** Audit the phase matrix,
   including correction, publication retention, cancellation and cleanup failure
   precedence, then replace each provider pipeline with the inherited lifecycle.

Each replacement removes the code it supersedes in the same PR. Preserve current
blocking/nonblocking and concurrency semantics. Do not keep a parallel fallback
runtime or describe equal-looking folders as completed unification.

Saved graphs need an explicit compatibility policy:

- Keep public component names, IDs, ports, runner HTTP/CLI contracts and the
  generic `integrations.langflow.agent.component` entrypoint stable.
- Inventory embedded component imports before retiring paths. Some current
  Claude component code directly imports its old provider catalogue, so keeping
  the generic entrypoint alone is insufficient.
- Where imports change, create a backed-up saved-flow/component revision using
  the public interface. Preserve node IDs, connections, settings, pinned skills
  and run references. Review a dry-run diff before applying the migration.
- Preserve historical originals. Migration must not submit or retry graph work.
  Unknown consumers or unrecognized component revisions remain migration blockers
  rather than being silently rewritten or declared compatible.

Validate installed-wheel resources, Docker contexts, entrypoints, imports, public
errors and persisted schemas. Use real per-provider graph evidence for changed
execution and Activity paths, the required Claude review, and owner inspection
before merge. A reviewed proposal does not establish implementation acceptance.

Measure production source size after each consolidation. Relocation alone does
not reduce code. The previously recorded baseline gap was +1,468 Python/mjs lines;
this document neither updates that measurement nor claims parity. Reinvestigate
or notify the owner if the completed consolidation does not reach the requested
parity.
