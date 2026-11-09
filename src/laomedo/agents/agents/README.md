# Agent implementations

Concrete providers and their shared abstract execution base live together so a
provider author can find both the extension contract and real implementations.
The wider application uses [the public interface](../interface/README.md).

| Concern | Package | Object nomenclature |
| --- | --- | --- |
| Abstract lifecycle | [base](base/README.md) | `BaseAgent`: abstract extension base |
| Codex implementation | [codex](codex/README.md) | `CodexAgent`: concrete provider |
| Claude implementation | [claude](claude/README.md) | `ClaudeAgent`: concrete provider |
| OpenCode implementation | [opencode](opencode/README.md) | `OpenCodeAgent`: concrete provider |

`Base` means abstract; provider names identify actual specializations. A provider
owns native authentication, discovery, launch policy, resources and interpretation.
It imports the base and public contracts, never another provider. Shared Docker
mechanics remain in py-docker; host grants and GitHub policy remain outside Agents.

Concrete providers retain execution overrides. Inherited lifecycle
consolidation requires separate implementation and real per-provider evidence.

## Provider role contracts (#275)

Provider names identify implementations of a role, not matching directories.
Shared behavioral contracts live in `base/base.py`; their typed values live in
`base/models.py`. There is no base subclass per provider merely for symmetry.
The wider application's interface remains `agents/interface/`.

| Role | Required vocabulary | Ownership and side effects |
| --- | --- | --- |
| `BaseAgentRuntime` / `{Provider}AgentRuntime` | `start`, `request_cancel`, `shutdown` | Launch/initialize the configured scope, retain exact native handles, request interruption, and close only owned resources. Results separate launched/ready, requested/confirmed cancellation, and confirmed/unknown cleanup. Codex/OpenCode scope is an attempt; Claude sessions are turn-scoped. ACP messaging is composed, not a lifecycle superclass. |
| `BaseCommandExecutor` / `{Provider}CommandExecutor` | `execute`, `shutdown` | Admit one typed command/deadline/cancellation context and report native exit/output separately from cleanup. HTTP/MCP command handlers adapt wire requests; they do not define the execution contract. Existing provider limits and mediation authority remain local. |
| `BaseInterruptibleCommandExecutor` | `request_cancel` | Claude/OpenCode own interruptible worker jobs. Stop admission, signal owned active jobs and return requested/unknown acknowledgement; `shutdown` separately waits for exact cleanup. |
| `BaseSplitCommandExecutor` | `check_health`, `assert_controller_isolated` | Codex's optional persistent native exec-server requires its reader/liveness and credential-controller isolation gate. Other providers do not emulate a persistent service to satisfy this capability. |
| `BaseCredentialProvider` / `{Provider}CredentialProvider` | `prepare`, `validate`, `borrow`, `release` | Provider-owned admission/refresh and exact temporary-state lifetime. Public bindings contain no secrets; borrowed material stays host-only. Releasing a borrowed profile does not revoke or delete host login. |
| `BaseModelCatalog` / `{Provider}ModelCatalog` | `discover(refresh=False)`, `snapshot`, `wait_until_idle` | Zero-turn discovery, provider-specific freshness and in-flight sharing. A snapshot is the last observed account catalogue, possibly stale, never a refresh or a selection change. Waiting observes discovery cleanup, not run admission. |
| `BaseActivityProjector` / `{Provider}ActivityProjector` | `accepts`, `project` | Recognize unqualified native observations and convert them to shared `ActivityProjection`; persisted provider identity takes precedence. Unknown usage remains unknown. Native pricing belongs to its provider. |
| `AgentProviderRegistry` | `descriptor`, `create_agent`, `activity_projector` | Trusted built-in registrations and typed `AgentProviderDescriptor` capabilities. External inputs can select only registered IDs, never imports, executables or credential locations. |

Readiness, process health and isolation return distinct typed observations; none
implies another. An unsupported check is unknown/unsupported, never success. No
interchangeable check coordinator exists, so no generic health-check ABC is added.
`AcpSession` remains the shared wire implementation without a redundant ABC.

`start` is a host-only class factory returning `RuntimeLaunch`: an opaque owned
runtime plus its initial observation. `shutdown` is asynchronous so exact native
session cleanup can finish before a confirmed result. OpenCode construction only
prepares an environment; launch becomes observed when its session is allocated.
Claude owns a turn session, with ACP readiness and native identity still owned by
the composed Agent communication path. Unknown observations do not certify either.

The concrete runtime/executor/credential roles live in each provider's
`runtime.py`, `executor.py` (Codex: `split/executor.py`) and `credentials.py`.
Claude's `policy.py` constructs admitted Docker specifications and lease policy;
its HTTP transport and OpenCode's MCP broker only adapt authenticated requests to
their executors. Model discovery lives in provider `catalog.py`: Codex/OpenCode
retain 30-second caches, Claude retains its 300-second cache and shared in-flight
refresh. Discovery never prompts a model.

Credential bindings contain public metadata; explicit host-only material access
keeps tokens excluded from representations and serialization. `release` does not
revoke borrowed credentials. Unsupported requested validity/deadline constraints
fail with `credential_constraints_unsupported` before refresh rather than claiming
they were enforced. Existing native refresh owners and credential paths remain.

`BaseCredentialProvider.borrow()` returns host-only `CredentialMaterial` for every
provider. Codex supplies a borrowed access token and public identity; volume/profile
providers prepare their existing native credential source and return its binding
without copying a token into the controller environment. Absence of an inline token
does not imply missing authentication. The material excludes secrets from dumps.

Catalogue cache state and observation methods belong to `BaseModelCatalog`; native
discovery, TTL and in-flight ownership remain provider-owned. `wait_until_idle`
waits for the observed discovery only; it does not reserve the provider or certify
successful discovery. `snapshot` does not certify freshness after a failed refresh.

Existing public payloads, persisted schemas, stable failure codes, native session
IDs and host authorization are preserved at explicit adapters. Native user-story
acceptance covers Fresh, Resume, status, cancellation, model refresh, Activity and
failure/recovery independently for each provider. Unit/socket/fixture checks do
not establish real-provider acceptance; this work authorizes no new model probe.
