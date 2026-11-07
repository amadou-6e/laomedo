# Agent architecture

The Agent module owns provider execution, working state, response contracts,
Agent coordination and observability. The wider app uses `interface/`; concrete
providers and their shared abstract implementation live together in `agents/`.

```text
agents/
  agents/
    base/                 BaseAgent, common ACP session and execution records
    codex/                CodexAgent, controller, split execution and resources
    claude/               ClaudeAgent, authentication, model discovery and Activity
    opencode/             OpenCodeAgent, authentication, history and Activity
  interface/
    bridge.py             HttpAgentBridge, the app-side runner client
    models.py             Canonical public Agent request/reference/status values
    output/               Shared response requirements and validation
    langflow/             AgentComponent, the Agent-specific framework adapter
  workspaces/             AgentWorkspace, preparation, baselines and pinned skills
  artifacts/              Retained Agent output selection and transfer
  orchestration/          AgentHandoffController and bounded Agent handoffs
  activity/               Shared normalized capture, storage and projection
```

## Boundaries and nomenclature

| Owner | Objects and vocabulary |
| --- | --- |
| [Implementations](agents/README.md) | `BaseAgent` defines the common lifecycle; `CodexAgent`, `ClaudeAgent`, `OpenCodeAgent` own provider policy, resources and native interpretation. Concrete providers do not inherit another provider. |
| [Public interface](interface/README.md) | `HttpAgentBridge` dispatches and reconciles admitted requests; `AgentRequest`, `AgentRunReference`, `RunnerStatusRecord` retain public payload identity. |
| [Workspaces](workspaces/README.md) | `AgentWorkspace` admits/prepares files using shared Git; canonical path/snapshot models own grouped state. |
| [Coordination](orchestration/README.md) | `AgentHandoffController` coordinates successive requests with explicit bounds; handoff provenance stays a canonical model. |
| [Activity](activity/README.md) | `ActivityStore`, `ActivityCapture` and projection functions retain and interpret Agent observations. Provider-native capture stays with that provider. |
| [Artifacts](artifacts/README.md) | Selection and import of retained Agent output; identity is not publication authority. |

`Base` denotes an abstract contract. Provider names identify real implementations;
other adjectives describe actual variants. Responsibility nouns identify the
interface. Each leaf README documents its supported methods and invariants.
Grouped contracts belong to canonical Pydantic `models.py`; settings have feature
ownership. Use defining object imports and module-level handlers.

Generic repository operations belong to `laomedo.git`. GitHub resource policy
belongs to `laomedo.github`; graph-side PR feedback and downstream contract
routing live under `integrations/langflow`. Graph execution correlation belongs
to `work_graph/runs`. Host authorization, publication, leases and API composition
remain outside Agents. `host/runner/http` serves the runner API; neighboring
runner startup/recovery services manage that API's lifetime. Mediation resources
belong to `host/mediation/resources`, not provider credential state.

The established public `integrations.langflow.agent.component` entrypoint delegates
to the Agent adapter for saved components. Python symbol names do not rename
persisted runner fields, stable machine codes or immutable history. Unknown saved
source revisions require explicit inspection and migration, never silent dispatch.

## Capability and evidence boundaries

Provider folders share the lifecycle contract, not necessarily every native
capability. Provider-specific READMEs describe supported behavior and constraints.
Source tests, installed-package checks and actual provider/graph validation are
separate evidence; current revision status lives in the
[integration record](../../../docs/architecture/agent-assembly.md).

Historical campaigns belong to permanent `exp`; production tests never fetch it.
The maintained [Agent builder](../../../examples/agents/README.md) exports current
component definitions with caller-supplied inputs. Compatibility data belongs to
the owning tests and is not a runnable example or new execution evidence.
