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
| `BaseCredentialProvider` / `{Provider}CredentialProvider` | `prepare`, `validate`, `release` | Provider-owned admission/refresh and exact temporary-state lifetime. Public bindings contain no secrets. Releasing a borrowed profile does not revoke or delete host login. |
| `BaseModelCatalog` / `{Provider}ModelCatalog` | `discover(refresh=False)` | Zero-turn discovery, provider-specific freshness and in-flight sharing. Refresh never silently chooses another model. Failed refresh does not certify stale data. |
| `BaseActivityProjector` / `{Provider}ActivityProjector` | `project` | Convert provider-native observations to shared `ActivityProjection`; unknown usage remains unknown. Native pricing belongs to its provider. Parsing helpers may remain functions. |
| `AgentProviderRegistry` | `descriptor`, `create_agent`, `activity_projector` | Trusted built-in registrations and typed `AgentProviderDescriptor` capabilities. External inputs can select only registered IDs, never imports, executables or credential locations. |

Readiness, process health and isolation return distinct typed observations; none
implies another. An unsupported check is unknown/unsupported, never success. No
interchangeable check coordinator exists, so no generic health-check ABC is added.
`AcpSession` remains the shared wire implementation without a redundant ABC.

Existing public payloads, persisted schemas, stable failure codes, native session
IDs and host authorization are preserved at explicit adapters. Native user-story
acceptance covers Fresh, Resume, status, cancellation, model refresh, Activity and
failure/recovery independently for each provider. Unit/socket/fixture checks do
not establish real-provider acceptance; this work authorizes no new model probe.
