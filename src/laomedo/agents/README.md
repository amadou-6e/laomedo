# Agent architecture redesign

**Status: PROPOSED, NOT IMPLEMENTED.** This document records the target design
discussed with the owner. It is not a description of the current folder layout,
a completed refactor, or approval to merge. The owner selected the nested
`agents/agents/{claude,codex,opencode,base}` layout and the Agent-only module
boundary below. Implementation contracts and migration still require the checks
below; earlier Claude reviews do not approve later edits or implementation.

The outer `agents/` module owns only Agent concerns. Its inner `agents/` package
contains concrete Agent implementations and their shared abstract base. Other
purely Agent-specific services are siblings of that inner package. The common
execution lifecycle is inherited through `BaseAgent`; matching folders must
reflect shared behavior rather than three independent pipelines.

For current product documentation, see the [Agents guide](../../../docs/features/agents/README.md).
Canonical requirements remain in the separate specs repository.

## Module boundary and owning objects

Paths in this table are relative to `src/laomedo/` and describe the target.

| Concern | Folder | Objects and responsibility |
| --- | --- | --- |
| Public Agent API | `agents/interface/` | `HttpAgentBridge`, `AgentRequest`, `AgentCapabilities`: the boundary used by the rest of the app |
| Shared Agent implementation | `agents/agents/base/` | `BaseAgent`, `AcpRuntime`, `AgentRegistry`: inherited lifecycle, communication and trusted registration |
| Concrete Agent implementations | `agents/agents/codex/`, `agents/agents/claude/`, `agents/agents/opencode/` | `CodexAgent`, `ClaudeAgent`, `OpenCodeAgent`: provider behavior and resources |
| Agent working state | `agents/workspaces/` | `BaseWorkspace`, `DirectoryWorkspace`, `GitWorkspace`: prepare, verify, snapshot and restore Agent working state |
| Agent artifacts | `agents/artifacts/` | `ArtifactStore`, `ArtifactReference`: retain, select, verify and transfer files between Agent runs |
| Agent run persistence | `agents/runs/` | `RunStore`, `RunRecord`, `RunReference`: Agent requests, attempts, state and recovery information |
| Agent response requirements | `agents/output/` | `OutputValidator`, `OutputRequirements`, `OutputValidation`: describe and check Agent responses |
| Coordination between Agents | `agents/orchestration/` | `AgentHandoffController`, `AgentHandoff`: coordinate Agent handoffs and explicit stopping conditions |
| Agent observability | `agents/activity/` | `ActivityStore`, `ActivityCapture`, `ActivityProjection`: retain and present normalized Agent activity |
| Agent framework integration | `agents/interface/` | Agent-specific framework adapters belong to the public boundary; the existing Agent component adapter is Langflow-specific |

The following concerns stay outside the Agent module:

| Concern | Owner outside `agents/` | Boundary |
| --- | --- | --- |
| Reusable Git mechanics | Shared Git code, with `repositories/git/` as a target after caller audit | `GitRepository` supplies controlled Git operations to Agent workspaces and other consumers |
| GitHub workflows and operations | Existing GitHub, work-graph and host publication/mediation owners | Issue/PR actions, repository authorization, workflow decisions and publishing are not Agent responsibilities |
| Graph dispatch persistence | `work_graph/`, with a focused runs package if warranted | Graph launch reservations and invocation correlations are distinct from Agent run records |
| General graph integration | `integrations/langflow/` | Cross-node PR/Skill feedback, downstream requirement discovery and graph routing stay with the graph integration |
| General infrastructure | Shared host services and `py-docker` | Secure storage, leases, mediation and Docker mechanics retain their existing owners |

Having an Agent as a caller does not make a GitHub workflow, graph execution or
general infrastructure operation Agent-specific. Conversely, an app viewer
reading Agent activity does not make that activity a general app concern.

Run-to-run handoff control through the public Agent interface belongs in
`agents/orchestration/`. Graph-wired loops between Agent, PR, Skill or other nodes
belong to the Langflow integration, including their scheduling and edge handling.

`Workspace` is a behavioral object, not a namespace for filesystem helpers.
`GitWorkspace` uses a `GitRepository` to prepare its working state. Reusable Git
mechanics already have consumers in Skills and host-side operations. A caller
audit must establish the exact shared operations and destination before moving
them; do not copy them into a second Agent implementation. GitHub grants, remote
selection and publication authorization stay with their non-Agent owners.

The owner's requested LangChain Agent integration belongs under
`agents/interface/langchain/` when an actual adapter is implemented. The current
Agent graph adapter is Langflow-specific and targets
`agents/interface/langflow/`. These are separate framework adapters, not two names
for the same implementation. This proposal does not claim a LangChain adapter
already exists or add a new framework dependency.

## Target structure

```text
laomedo/
├── agents/                         # Only Agent-specific concerns
│   ├── agents/                     # Agent implementations
│   │   ├── claude/
│   │   ├── codex/
│   │   ├── opencode/
│   │   └── base/
│   │       ├── agent.py            # BaseAgent
│   │       ├── runtime.py          # AcpRuntime
│   │       ├── registry.py         # AgentRegistry
│   │       ├── catalog.py          # Shared discovery coordination
│   │       ├── models.py
│   │       ├── settings.py
│   │       └── acp/                # Shared Agent protocol implementation
│   ├── interface/                  # Boundary with the wider implementation
│   │   ├── bridge.py               # HttpAgentBridge
│   │   ├── models.py               # Public Agent requests and descriptors
│   │   ├── errors.py               # Public error exports
│   │   ├── langflow/               # Agent-specific component adapter
│   │   └── langchain/              # Only when an actual Agent adapter is added
│   ├── workspaces/
│   │   ├── base.py                 # BaseWorkspace
│   │   ├── directory.py            # DirectoryWorkspace
│   │   ├── git.py                  # GitWorkspace, using shared Git mechanics
│   │   └── models.py
│   ├── artifacts/
│   │   ├── store.py                # ArtifactStore
│   │   └── models.py
│   ├── runs/
│   │   ├── store.py                # RunStore for Agent runs
│   │   └── models.py
│   ├── output/
│   │   ├── validator.py            # Agent response validation
│   │   └── models.py
│   ├── orchestration/
│   │   ├── controller.py           # AgentHandoffController
│   │   └── models.py
│   ├── activity/                   # Common Agent activity only
│   ├── errors.py                   # One shared Agent error hierarchy
│   └── ADD_PROVIDER.md
├── repositories/                   # Shared Git target, after caller audit
│   └── git/
├── github/                         # GitHub domain and workflow operations
├── work_graph/                     # Graph execution and dispatch persistence
├── host/                           # Shared host infrastructure/publication
└── integrations/
    └── langflow/
        ├── agent/                  # Stable external component entrypoint
        ├── feedback/               # Cross-node PR/Skill and Agent graph loops
        └── output/                 # Downstream discovery and graph routing
```

Settings, errors and package initializers are omitted from parts of this tree
for readability. Introduce them where the concern needs them. Do not create
empty files or duplicate models solely to make folder contents identical.
`ADD_PROVIDER.md` is a planned extension guide, not an existing runnable example.

## Provider ownership

Each provider has the same core responsibilities. Codex illustrates the layout:

```text
agents/agents/codex/
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
actual capabilities, such as `agents/agents/opencode/activity/history/`.

Provider-specific authentication logic, catalogue discovery, native Activity
interpretation, runtime resources and policy extensions belong with the provider.
Common `agents/activity/` code receives registered adapters and canonical records
without provider-name branches. Native interpretation stays inside
`agents/agents/<provider>/activity/`, superseding the earlier top-level Activity
proposal. Original native evidence remains separately retained with provenance.

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

`BaseAgent`, defined in `agents/agents/base/`, supplies the inherited common
lifecycle for all providers and coordinates
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
  implementations in `agents/agents/`. Explicit host bootstrap and runner-server
  wiring are the exceptions: they register trusted factories and delegate to the
  base. Import-boundary checks must identify those entrypoints explicitly.
- The interface imports domain models, not base or provider implementations.
  It re-exports canonical models from their owning concern where necessary.
- The base depends on those public data contracts and shared domain objects.
  Concrete providers depend on the base.
- Agent-specific framework adapters are part of `agents/interface`. They may
  depend on the relevant optional framework, but importing the core Agent module
  must not eagerly load Langflow or LangChain. General graph traversal and
  GitHub/Skill feedback orchestration remain outside the Agent module.
- Host startup selects explicit trusted provider factories. The registry does
  not automatically execute factories advertised by installed packages.
- A graph selects a configured provider ID. It cannot supply import paths,
  commands or credential locations.
- Move the existing Agent `RunnerError` hierarchy and its stable machine codes
  into `agents/errors.py`; `agents/interface/errors.py` only re-exports it. Do not
  define a parallel hierarchy or lose catalogue coverage. Graph and host error
  families remain with their respective owners outside the Agent module.

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
| `AgentHandoffController` | Coordination of handoffs between Agent runs; mandatory limits are behavior/settings, not a separate controller variant |
| `CodexActivityProjector` | Conversion of native evidence to the common Activity model |

Reserve `Ledger` for ordered, append-only facts. The Agent-run portion of mutable
execution persistence should be named `RunStore`; graph dispatch persistence
remains separate under `work_graph/`. Use `Full`, `Async` or `Sync` only when
they distinguish precisely defined supported variants. This proposal does not
introduce an async-core conversion or parallel sync/async execution pipelines.

Keep one canonical Pydantic model per structured concept in its owning
`models.py`, with described fields. Put externally supplied configuration in
Pydantic settings objects in `settings.py`. Keep behavioral methods with their
owning objects and standalone functions in focused function-only modules.

## Adding a provider

The extension guide and shared conformance suite must make these steps explicit:

1. Create the implementation package under `agents/agents/<provider>/`.
2. Subclass `BaseAgent` from `agents/agents/base/` and implement its documented hooks.
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

1. **Separate ownership and relocate existing behavior.** Put concrete Agents and
   the base under `agents/agents/`; keep purely Agent-specific services beside that
   package. Separate graph dispatch records, GitHub workflows and reusable Git
   mechanics into their non-Agent owners. Move only Agent-specific framework
   adapters into `agents/interface`. Initially `BaseAgent` is the current shared
   Runner renamed and relocated, with existing provider overrides retained. This
   step alone does not complete lifecycle consolidation.
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
  generic `integrations.langflow.agent.component` entrypoint stable. Its Agent
  implementation moves to `agents/interface/langflow/`; the established public
  entrypoint delegates there rather than retaining a second implementation.
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
