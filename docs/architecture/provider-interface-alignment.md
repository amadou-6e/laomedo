# Provider interface alignment

The reviewed target and completion criteria are tracked in [#277](https://github.com/amadou-6e/laomedo/issues/277) and [the canonical draft design](https://github.com/amadou-6e/specs/blob/feat/shared-acp-agent-protocol/projects/laomedo/subsystems/agent-execution/design/provider-roles.md). The analysis below describes the interim implementation, not the approved final object boundaries. In particular the target retains `BaseAgentRuntime` with shared Docker mechanisms; it separates drivers from resource scopes and removes symmetry-only capabilities.

The initial exception-aware-cleanup rationale below is incomplete: `AcpSession.close` currently closes Docker before the later context exit. The target gives process cleanup exclusively to runtime and exposes a stream without close access to ACP. SDK disconnect cancels tasks; controller EOF is required before the owning `asyncio.run` shuts its blocking-reader executor down.

The role objects introduced by #275 exposed native operations beyond their base
contracts. The CI guard intentionally reports those gaps. Alignment must move
responsibilities and actual callers, rather than add every native method to a
large base or rename external calls to private helpers.

## Aligned operations

| Concern | Shared contract | Native difference retained |
| --- | --- | --- |
| Model catalogue | `discover`, `snapshot`, `wait_until_idle` | Codex/OpenCode retain 30-second caches; Claude retains its 300-second cache and shared in-flight Future. A snapshot may be stale; waiting does not certify success or reserve admission. |
| Credential source | `prepare`, `validate`, `borrow`, `release` | Codex borrows an inline host access token. Claude/OpenCode keep native volume/profile secrets in place. `CredentialMaterial` represents either binding without forcing token copies. Authentication outcomes retain their native scope. |
| Activity | `accepts`, `project` | Recognition and interpretation remain native; canonical output and unknown usage/cost semantics are shared. Stored provider identity takes precedence. |
| Command execution | `execute`, `shutdown` | Claude/OpenCode run isolated transient workers; Codex's optional split mode owns a persistent native exec-server. Cleanup confirms only the named owned scope. Public `close` aliases are removed and callers use `shutdown`. |

`BaseInterruptibleCommandExecutor` is a genuine additional capability implemented
by Claude and OpenCode. Both own an active worker cancellation signal. Calling
`request_cancel` stops admission and signals active jobs; it does not wait for
cleanup or invent native acknowledgement. A subsequent `shutdown` waits for
owned workers and transport closure.

Codex's host-side bounded probe executor does not own the native model command's
interruption signal: its optional persistent exec-server is registered with the
Codex ACP adapter. Prompt interruption belongs to that native protocol. Stopping
the entire persistent service would have different consequences from cancelling
one worker, so Codex does not claim the interruptible-worker capability.

`BaseSplitCommandExecutor` declares Codex's native persistent-service health and
controller-isolation gate. Claude/OpenCode have no corresponding persistent
exec-server/reader to check. Their per-job isolation is enforced in Docker launch
policy, not established by pretending the Codex split gate exists. This is a
topology-specific capability with an actual consumer, not a compulsory method
returning success or unsupported on every provider.

These changes align callable roles. They do not establish that all provider
configuration, native resource state or orchestration is already interchangeable.

Remaining cross-object coupling also needs attention: catalogue implementations
still call native Agent discovery hooks; command transports inspect executor
locks/flags; Codex registration reads native executor fields; and runtime launch
returns an opaque handle from provider-specific constructor arguments. Those
boundaries need explicit injected callback/state/factory contracts in the next
ownership pass. The public-surface guard does not establish that those accesses
are fully declared or type checked.

## Runtime divergence that remains

| Runtime | Current ownership and outside calls | Why the lifecycle base is insufficient |
| --- | --- | --- |
| Codex | An attempt controller, shared ACP session, native extension policy and optional persistent executor. Agent callers invoke handshake, model discovery, native session opening, prompt, preflight and split isolation methods. | Container ownership, native communication and readiness/discovery policy are combined. The Agent also reads native events and executor state directly. Those operations are not generic container lifecycle operations. |
| Claude | A leased controller session for one native turn. The Agent owns ACP communication and uses the runtime as a context manager. | `with` propagates the original execution exception into py-docker's creator-thread cleanup context. Replacing it with an unconditional close could lose native failure/cleanup evidence. Several turns can allocate several controller scopes while resuming one persisted native session. |
| OpenCode | A prepared environment followed by an attempt controller, MCP command workers, native metadata/history jobs and an embedded ACP run sequence. | Construction is not process launch. `run` includes handshake/session selection/prompt/capture, while history export follows confirmed closure. A generic start/close pair cannot hide those ordering and ownership guarantees. |

The same word "session" currently names three different things: a Docker process
scope, an ACP connection, and a persisted native conversation identity. A common
interface must distinguish them. Neither a process restart nor a new container
necessarily creates a new native conversation.

## Next runtime boundary

Keep `BaseAgentRuntime` responsible for an explicitly scoped resource lifetime:
configured launch, resource observation, cancellation admission and exact cleanup.
Move native handshake/prompt/extension/history orchestration behind an
attempt-level provider contract composed with that runtime. Catalogue and
credential services retain their own contracts. Shared callers should receive
typed role handles, rather than opaque objects requiring native method discovery.

The attempt boundary must preserve Fresh/Resume identity, zero-turn discovery,
authorization checks, output precheck, native cancellation acknowledgement and
failure-first cleanup. It must allow Claude to allocate turn scopes internally
without promising that one attempt always has one controller process. It must
not make OpenCode's preparation report a launched process, or let a command-job
result certify controller cleanup.

No fundamental provider limitation prevents architectural alignment at those
boundaries. The remaining work is a substantial ownership/sequencing refactor.
Adding Codex RPC methods, Claude context-manager methods and OpenCode history/run
methods indiscriminately to `BaseAgentRuntime` would obscure that work.

The CI guard remains active for the unresolved runtime methods. Its static
surface/signature checks do not prove absence of arbitrary dynamic/private/state
access or establish real-provider behavior. Native Fresh/Resume/cancellation and
failure/recovery acceptance still requires the owner's real-workflow validation;
no new model probe is authorized by these structural changes.
