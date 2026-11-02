# Agent ownership

The Agent module owns provider execution, Agent working state, response contracts,
handoffs and Agent observability. Git operations belong to `laomedo.git`; GitHub
resource policy belongs to `laomedo.github`; host authorization, publication and
lease supervision remain host responsibilities. Graph scheduling and execution
correlation belong to `laomedo.work_graph`.

## Current interfaces

`runtime.Runner` is the current abstract durable lifecycle. Concrete Codex,
Claude and OpenCode runners live under `providers/`. `contracts/` owns the
current response contract; `handoffs/` coordinates Agent handoffs. The source
layout and provider protocols on develop are not yet the selected target below.
An older integrated branch contains candidate changes, not independently accepted
implementation. Its source is reviewed and selected by concern, never merged wholesale.

## Selected target (not yet implemented in this branch)

```text
agents/
  agents/
    base/                 BaseAgent and common execution lifecycle
    codex/                CodexAgent, provider auth/activity/resources
    claude/               ClaudeAgent, provider auth/activity/resources
    opencode/             OpenCodeAgent, provider auth/activity/resources
  interface/
    output/               shared Agent response validation contract
    langflow/             Agent-specific graph adapter
  workspaces/             AgentWorkspace and working-state preparation
  artifacts/              retained Agent output selection and transfer
  orchestration/          AgentHandoffController and bounded handoffs
  activity/               common normalized Agent observability
```

The nested `agents/agents` layout is the owner's selected design. Provider
packages are first-class discoverable implementations beside `base`; their
provider-specific authentication, telemetry and resources have the same owner.
The public `interface` is the app-facing contract; the inherited implementation
under `base` is an extension point, not the public app dependency.

## Object and method nomenclature

| Object | Responsibility and method vocabulary |
| --- | --- |
| `BaseAgent` | Abstract shared lifecycle: `start`, `start_async`, `resume`, `status`, `cancel`; common reservation and terminal-state guarantees. |
| `CodexAgent`, `ClaudeAgent`, `OpenCodeAgent` | Concrete provider policy and execution; inherit lifecycle responsibilities rather than a concrete provider. |
| `HttpAgentBridge` | App-facing Agent transport: `start`, `resume`, `status`, `cancel`; preserve existing request/response shapes. |
| `AgentWorkspace` | Admit source, prepare working files, verify and snapshot state using shared Git mechanics. |
| `AgentHandoffController` | Coordinate successive Agent runs with explicit bounds and outcomes. |
| `ActivityStore`, `ActivityCapture`, `ActivityProjection` | Retain, normalize and present Agent observations; raw provider events remain provider-owned. |
| `OutputRequirements`, `OutputValidation`, `OutputValidator` | Public response expectations and checking; belong to `interface/output`. |

Use `Base` for actual abstract contracts, a meaningful adjective only for real
variants, and a final responsibility noun. Each implementing leaf README owns
its actual methods and invariants. Canonical grouped records use Pydantic in
`models.py`, described fields, validation and explicit boundary projections.
Externally supplied settings use feature-owned `settings.py`. Implementation
files introduce classes or independent functions, never both. Import defining
objects directly; nested handler definitions have module-level owners.

## Relocation ownership decisions

| Existing concern | Selected destination / boundary |
| --- | --- |
| `workflow/store.py` | `laomedo.work_graph/runs`: graph-side correlation and persisted workflow state, not Agent-owned run storage. |
| `feedback/pr.py` | GitHub PR feedback policy outside Agents; coordinate with independent GitHub work to avoid conflicting owners. |
| `contracts/graph.py` | `laomedo.work_graph`: downstream graph contract discovery; output validation remains `agents/interface/output`. |
| `runtime/serving.py` | Trusted runner HTTP service under `host/runner/http`, composing the abstract Agent; app-side bridge under `agents/interface`. Preserve lazy imports. |
| Codex servers/preflight | `agents/agents/codex`: provider-native controller, transport and pinned probe policy/resources. |
| `resources/mediation/*.mjs` | Shared Agent-container mediation resources under Agent resources; host owns authorization, GitHub owns resource policy. No mailbox rewrite is implied. |
| Current `laomedo.activity` | Agent-native capture/projection under `agents/activity`; reusable observability interfaces outside remain separate only with actual non-Agent consumers. |
| Current public graph component | Keep established `integrations.langflow.agent.component` entrypoint for existing saved graphs; implementation delegates to `agents/interface/langflow`. |

Current names are `runtime.runner.Runner` (abstract), `CodexRunner`,
`ClaudeRunner`, `OpenCodeRunner` (all inherit that abstract Runner). Older
`LocalRunner` names in tests/migration records are aliases, not another lifecycle.
Renaming requires complete caller and persisted-contract inventory first.

The initial import cleanup covers exception/model symbols in `runtime/runner.py`
only. Dynamic function-module bindings stay unchanged, including `_json`, because
fault-injection controls patch the defining helper. Provider aliases and the lazy
`runtime/serving.py` import remain unchanged. Later helper-binding changes require
an explicit defining/consuming patch-target map and mutation evidence that injected
faults still exercise the intended consumer.

## Compatibility and verification

Preserve public component names/ports, HTTP and CLI entrypoints, saved graph
identities, wire/persisted records, stable error codes, credential boundaries,
replay, cancellation and cleanup uncertainty. Migrate maintained callers and
recognized saved source/templates together. Unknown external saved flows remain
an explicit compatibility gap. Do not create facades without a real consumer.

A folder move does not prove lifecycle or ACP unification. Existing per-provider
capabilities remain explicit. Protocol adoption beyond accepted develop behavior
is separately selected and reviewed; historical ACP evidence is not new acceptance.
No model request, credential copy or GitHub operation is triggered by restructuring.

Maintained examples are consolidated around supported workflows. Exact historical
campaigns are preserved on permanent `exp` before removal; production regression
tests neither import campaigns nor fetch that branch. Agent tests are grouped by
concern under `tests/test_agents/test_*`, with descriptive support-only helpers.
Real provider/graph evidence, installed-package checks, full independent review
and requesting-owner workflow validation are separate merge requirements.
