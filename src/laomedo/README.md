# Laomedo implementation ownership

Packages follow the concern they implement. Git execution, GitHub authorization,
publication and graph scheduling have their own owners even when an Agent calls them.

```text
laomedo/
  activity/                 Retained activity capture, projection and runner feeds
  agents/                   Provider implementations and Agent-specific lifecycle
    runtime/                Shared lifecycle
    providers/              Codex, Claude and OpenCode execution
    contracts/              Agent output and component request boundary
  git/                      Native Git execution, repositories and working trees
    windows/                Owned process-tree containment for bounded reads
  github/                   Issue/PR operations and authorized GitHub transport
  skills/                   Sources, immutable registry, edits and inspection
    interface/              Source and operation HTTP/CLI adapters
  host/                     Trusted local services, authority and publication
    credentials/            Host connection and authentication boundaries
    private_state/          Permission effects and private-directory admission
    mediation/              Host admission, journal and effect dispatch
    publication/            Bundle, handoff, ingress and verified-stage owners
  work_graph/               Work snapshots, dependencies, launch grants and dispatch
  integrations/langflow/    Cross-node graph integration and service composition
  http/                     Neutral redirect policy
```

## Object and method vocabulary

| Role | Objects and responsibilities |
| --- | --- |
| Native execution | GitCommandRunner.run executes a GitCommand within its GitExecutionContext and optional GitExecutionBudget |
| Working state | GitRepository owns object/ref mechanics; GitWorkingTree owns checked-out state; callers retain admission and authority |
| Skill persistence | SkillStore retains immutable bytes and commit history; SkillOperations validates atomic edits |
| Host records | OAuthAccount, OAuthAttempt, MediationServiceRecord, AuthorizedLeaseScope and publication records live in their feature models.py |
| Graph records | WorkSnapshot, WorkLaunchBinding, WorkLaunchGrant and WorkLaunchResult preserve snapshot, grant and dispatch boundaries |
| App boundary | Skills interface clients/handlers/servers adapt domain operations; graph and provider adapters preserve their existing public contracts |

Field-bearing records use canonical Pydantic models. Constructors and to_record or
to_payload projections preserve wire omission, nulls, ordering, hashes and private
storage. A model never grants authority. Feature settings live in settings.py;
errors.py documents stable failure categories and outcome guarantees.

Import the defining object or function directly. Preserve deliberate lazy imports
when they keep optional dependencies or construction cycles out of ordinary imports.
Standalone helpers stay separate from class implementations. A Server owns its
lifetime; a module-level RequestHandler owns protocol handling.

The owning README defines leaf interfaces and supported method names. Package and
internal-test checks establish structural or contract properties; live provider,
browser and user acceptance require their separately recorded evidence.
