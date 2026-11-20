# Codex Agent

## Interrupted-session continuation

`models.py` owns `ResumeCheckpoint`: a binding between one settled attempt,
its existing native thread, frozen workspace digest and current runner instance.
It is separate from successful output artifacts. Failed/cancelled attempts keep
their outcome, `snapshot_ready=False` and no output reference. The finalizer
creates a checkpoint only after confirmed controller/worker cleanup, closed
streams, matching native session and successful protected-workspace freezing.
`CodexAgent._resume_checkpoint` verifies these attempt-local facts again;
`resume` retains image/account/configuration and exact workspace checks. Native
load must return the original session. Restart, missing session, uncertain
cleanup and publication-owned runs do not gain continuation. The application
must separately reconcile tool-save receipts and revoke the prior tool grant
before offering another prompt; checkpoint existence is not tool authorization.

`CodexAgent` is the provider-qualified concrete Agent. It inherits the [abstract lifecycle](../base/README.md).
The implementation is in `agent.py`; folder and object renaming do not
remove its whole-pipeline overrides.

`CodexAgentRuntime` in `runtime.py` owns exact controller lifetime and composes
shared ACP communication. `CodexCommandExecutor` in `split/executor.py` owns the
optional split command scope. `CodexCredentialProvider` in `credentials.py`
borrows host-native access; `CodexModelCatalog` in `catalog.py` owns discovery.
`read_activity` with internal `activity/projection.py` helpers owns native interpretation and
the pinned pricing catalogue. See the [role methods](../README.md#provider-role-contracts-275).

A controller and optional executor span the attempt and output corrections. Native precheck and split-executor guards remain explicit.

| Method vocabulary | Provider contract |
| --- | --- |
| `runtime_binding()` | Public provider/runtime identity metadata; never credentials. |
| `model_catalog()` | Native model/effort discovery without a model turn. |
| `preflight()` | Check configured readiness/isolation; do not dispatch work. |
| `resume(...)` | Continue only an admitted existing provider/session binding. |
| `recover_interrupted(record)` | Reconcile exact recorded resources, without replaying execution. |
| `_execute(...)` | Protected provider hook implementing execution and finalization. |

Native `activity/` belongs to this provider. Codex's ChatGPT connection and secure
storage remain host-owned under `host/credentials/siwc`; no provider `auth/`
package is implied. `settings.py` owns protocol pins/configuration; `models.py`
owns structured values where present. No empty auth/model modules are required
for symmetry. Provider-independent secure storage, grants and Docker mechanics
retain their shared owners. Sibling provider imports are forbidden.

Start/resume/status/cancel use the base contract. The interface must explicitly
report unsupported capabilities and preserve unknown usage or partial evidence.
Successful execution, capture completeness and cleanup confirmation remain
separate facts. Existing stable error codes and persisted records do not change
with the Python object name.

## Failure finalization

Every noncompleted attempt, including early cancellation returns, retains a
private `AttemptFailureRecord` after ordinary run/attempt writes. A terminal
cancellation with supervision loss is attributed to `lease_service_lost` when no
earlier failure was observed. Later supervision loss never replaces an earlier
SDK or execution failure. The first `LeaseLossObservation` (or unavailable reason) remains in the
exact private lease directory, correlated through existing ownership; no public
payload extension is introduced. Unknown dynamic codes are deliberately omitted.

The primary failure survives later close, snapshot and lease-finish failures.
`LeaseClient.result` retains an actual result before a lost-lease rejection.
Project it through `LeaseCleanupObservation`: no result means no cleanup fact,
not false. The sidecar's lease cleanup boolean covers only that leased resource.
The existing public fail-closed status/category wins even beside verified cleanup.
Fresh native answers, counters and completion never establish Resume success.
# Native assistant commands

`commands.py` owns `CodexCommands.validate` (fixed built-in argument policy),
`admit` (exact native catalog revision/name) and `project` (bounded discovery,
including unavailable commands). Descriptions are never authority. The initial
admitted commands are status, mcp, skills, review and compact. Branch/commit
reviews are unavailable because the assistant uses scratch space, not a selected
repository; account, title, autonomous-goal and configuration controls are excluded.

`CodexAgentRuntime.command_catalog` observes the current ACP session without a
request. Explicit command mode is carried in the resume identity, never inferred
from prompt text. `prompt(..., command=...)` preserves strict native evidence for
model commands. `CodexCommandResult` in `controller/models.py` describes a native
control response without inventing a model turn ID or usage. Control completion
requires actual ACP end-turn text and no native turn events. Agent settlement
retains these as separate command receipts and preserves workspace checkpoints.
# Initial status

Codex admits `initial_native_command="status"` only with the exact task `/status`,
without output requirements or GitHub mediation. It opens the fresh native
session, observes the actual supported command catalog, and executes the existing
non-model control path with that catalog revision. The normal retained run,
thread, Activity, cleanup and workspace checkpoint support subsequent resume.
Absent handler support or advertisement fails before a prompt; no model fallback.


## Saved account connections

`connection.py` is the provider boundary. CodexConnection owns pending broker login attempts, begin/complete/progress/cancel, staged publication and readback, duplicate identity checks, exact token borrowing and local revision cleanup. PendingLogin belongs to models.py; login failure categories belong to settings.py. The shared Agent connection service owns admission/index fencing; host storage and profile authorization remain separate.

## Zero-turn session lifetime (implementation in progress)

The user selected retaining the actual Codex controller between an initial
`/status` and the first model message. A status receipt is completed independently
of native-resource cleanup. It does not claim a persisted model conversation.

- `CodexSessionOwner` in `session.py` owns the dedicated native event-loop thread
  and its event loop. `run()` executes on that thread; `close()` shuts down
  the loop after the Agent drains its native resources. `IdleCodexSession` in
  `models.py` groups the exact runtime, cancellation, lease and ownership values. No provider
  object is reconstructed from a saved pointer after restart.
- `CodexAgent` retains only successful zero-model-turn command sessions. The first
  ordinary message uses the same ACP session and native thread, with the selected
  model/effort configured in place. After a materialized model turn the normal
  close-and-resume path applies. Missing live state never creates another thread
  or submits a replacement prompt.
- The retained MCP registration keeps the native tool endpoint stable. Host tool
  authority is removed after status and remains unavailable while idle. Before
  the next message the assistant binds that endpoint to the newly authorized
  message context for the exact owner/conversation/account/generation. The frozen
  manifest cannot expand. After the first normal turn the registration is revoked.
- `BaseAgent.has_live_session(run_id)` reports actual in-memory ownership; its
  default is false. `BaseAgent.close()` is the shared teardown entry point. The
  saved-account manager uses these declared methods for settlement, disconnect
  inventory, cancellation and shutdown. Durable completed status receipts are
  not treated as proof that retained resources are absent.
- Idle resources stay under the same Docker ownership receipt, daemon, profile
  and native identity. Account revocation, cancellation, idle expiry, process
  failure and shutdown close that ownership; cleanup uncertainty stays explicit.
  A fresh credential observation is required before the first model turn.
  Routine token rotation for the same admitted account updates the existing
  controller with `CodexAgentRuntime.refresh_credential(token)`. Account identity
  and generation changes still refuse before dispatch; no thread is replaced.
- Managed SIWC uses pinned native command-backed bearer authentication. The fixed
  `/bin/cat /tmp/laomedo-provider-auth/access-token` helper reads a controller-only
  0600 file inside a 0700 noexec tmpfs, outside persistent profiles and tool mounts.
  `LaomedoLaunch.writeProviderCredential` atomically replaces that file; launch
  preparation removes ACCESS_TOKEN from the native child environment. The native
  provider retains https://api.openai.com/v1, Responses and HTTP streaming.
  `LaomedoExtension.refreshCredential` is a host-only ACP extension, requires the
  managed split executor, rejects updates during prompting and acknowledges only
  after the pinned 1 ms bearer cache expires. No paths, commands, refresh tokens
  or native RPC methods are supplied by callers. The Python runtime redacts each
  replacement token before sending it. Missing capability or uncertain update
  refuses dispatch and triggers normal owned cleanup.
  This managed credential path applies to graph and assistant saved-account runs.
  Both require the registered commands4 adapter capability; an explicit older
  image override is refused before inference rather than using stale credentials.
- Restart reconciles the retained resource receipt and marks that zero-turn
  session unavailable. It cannot claim the native thread survived: Codex has not
  written a rollout before its first user turn.

Acceptance requires real `/status`, first model message and contextual follow-up
with one native thread, working Laomedo MCP under the new message context, and
confirmed idle cleanup on shutdown/disconnect. Unit tests alone do not establish
that acceptance. This section describes the selected target, not completed work.

`controller/settings.py` owns `Settings.idle_session_seconds`
(`LAOMEDO_CODEX_IDLE_SESSION_SECONDS`, default 3600). It bounds unused resources;
it does not reduce the existing model-turn execution budget. Expired or
lost zero-turn sessions require an explicit new conversation.

## Idle OAuth renewal

`CodexAgentRuntime.check_health(idle=True)` checks the same saved-account identity
and connection epoch as active execution. Only an idle controller may wait up to
30 seconds for `refresh_in_flight` (the broker HTTP timeout is 20 seconds). It
never dispatches inference in that state. Unknown renewal, revoked admission,
changed identity/epoch or a stuck refresh closes the controller. Resume must
borrow an active token and confirm its native update before any prompt.
`live_session_close_reason` retains a fixed sanitized reason for idle cleanup;
unrecognized health errors become `health_lost`, never arbitrary exception text.
