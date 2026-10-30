# Laomedo implementation ownership

Packages follow the concern they implement. A caller being an Agent does not
make Git, GitHub, publishing or graph scheduling Agent-specific.

```text
laomedo/
  agents/                    Agent implementations and Agent-only services
    agents/{base,claude,codex,opencode}/
    interface/               Public Agent contracts and framework adapters
  github/                    Issue/PR admission, effects and delivery policy
  git/                       Reusable Git execution and working trees
  skills/                    Source selection, immutable content and atomic edits
  host/                      Local service composition and trusted infrastructure
  work_graph/                Work selection, dispatch and graph correlations
  integrations/langflow/     Cross-node graph scheduling and integration
  http/                      Small neutral HTTP mechanisms
```

The GitHub and Skills READMEs define their more detailed ownership targets.
Agent working-state admission belongs to `AgentWorkspace`; general Git execution
belongs to `git/`. Agent-specific skill materialization belongs to the Agent
workspace owner. Graph launch records are distinct from an Agent's own run state.

## Object and method vocabulary

| Role | Names and ownership |
| --- | --- |
| Abstract implementation contract | `BaseAgent`; concrete `CodexAgent`, `ClaudeAgent`, `OpenCodeAgent` inherit shared behavior |
| Public app boundary | `agents/interface/`, GitHub/Skills `interface/`; contracts and concrete app adapters are discoverable together |
| Working state | `AgentWorkspace` owns Agent admission; `GitRepository`, `GitWorkingTree`, `GitCommandRunner` own reusable Git operations |
| Persistence | `ActivityStore`, `SkillStore`; use Store for objects that own retained state |
| Authorized behavior | `SkillOperations`, `GitHubIssueGateway`, `GitHubPRGateway`; identities do not grant authority |
| HTTP lifetime and protocol | A `*Server` owns state and lifetime; a module-level `*RequestHandler` owns request handling |
| Correlated values | Canonical Pydantic records live in the owning feature's `models.py` |
| Configuration | Feature-local `settings.py`; external configuration uses a Pydantic settings object |

Use an adjective only for a real variant, followed by its responsibility noun.
Introduce an abstract Base only where an actual contract requires one. Leaf
READMEs define object methods before a new implementation or responsibility
change. Values and standalone helpers remain in separate implementation files.

## Defining-symbol imports

Import a class, function or constant directly from its defining module and use
that name. A descriptive symbol alias can distinguish two actual meanings.
Avoid importing a feature module solely to repeat its prefix at every use.

Preserve deliberate lazy imports inside composition functions and methods when
they prevent optional dependencies or cycles from loading prematurely. Direct
imports do not authorize lifting those imports to module scope. TYPE_CHECKING
imports remain type-only. Migration tools and test patch targets must follow the
actual defining owner; no forwarding modules are introduced to hide old imports.

Source structure, internal checks and independent review do not establish live
provider or graph acceptance. Final validation remains a separate recorded gate.
