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


## Saved-account quota discovery

`CodexAgent.subscription_limits()` uses the same `_discovery()` temporary lifecycle
as model discovery, with the selected credential provider and exact close receipts.
`CodexAgentRuntime.subscription_limits()` admits only the empty-parameter
`laomedo/codexRateLimits` extension. The adapter forwards exactly
`account/rateLimits/read` before any session/prompt. `CodexRateLimits.to_snapshot()`
projects native wire fields into canonical `SubscriptionSnapshot` models in
`agents/base/models.py`; malformed scalar fields stay unknown, malformed shapes
fail. No model turn, native thread, generic RPC forwarding or ambient login is added.
## Saved account connections

`connection.py` is the provider boundary. CodexConnection owns native device login, lease-bound details, explicit replacement confirmation, publication/readback, cancellation and native cleanup. CodexLoginAttempt belongs to models.py; native expiry and cleanup bounds belong to settings.py. `retained.py` supports only operational borrowing and erasure of already-saved token-sharing revisions until they are replaced or disconnected; it has no sign-in entry point. The shared Agent connection service owns admission/index fencing; host storage and profile authorization remain separate.


## Unified native connection (#300, implementation in progress)

Settings will expose one native ChatGPT device sign-in for both execution and
quota. `docker/codex-acp/native-login.mjs` is a fixed auth-only client:
projectDevice validates the exact official origin, login ID and bounded code;
projectIdentity admits only a ChatGPT account and matching public account IDs
from account/read.workspaceRouting and account/rateLimits/read. Missing IDs,
conflicting observations and unsupported routing fail closed. No token file is
read or decoded. Auth-file existence is checked only after the client stops.
The native child has an explicit environment and pinned issuer/file-store mode.
Its public device handoff is intended only for the originating browser lease.
The managed image installs and tests this helper. Settings uses a lease-bound
device handoff, with explicit confirmation before any saved-login replacement.
Native account/workspace plus email is an observed binding, not an immutable
per-user ID: email changes require confirmed replacement. Runtime admission and Agent launches use the same owned native profile and writer
lease as quota reads. Live acceptance, UI verification and full integration review
remain pending. Existing saved connections are untouched until confirmed replacement.

### Native credential custody

`native.py` owns CodexNativeCredentials. create records exact daemon/image/volume
ownership before creation; profile admits only that existing owned volume; lease
serializes one native writer across host processes and reconciles exact registered
session receipts before granting it; register records a creator receipt before
launch; erase recovers those receipts before removing only the labelled volume.
The lock spans client startup through confirmed cleanup. Docker outages preserve
custody and refuse new use. No method reads or exports the native auth file.
CodexNativeProfile and CodexAccountIdentity live in models.py. Identity is an
observed email/account binding; subject_hash is not a claim of immutable user ID.
These boundaries must be wired into login, discovery and every Agent launch before
native saved connections can be exposed.
Native identity projections are validated by `CodexConnection.validate_native_identity`,
which rejects a public observation that does not match the saved account binding.
The shared saved-connection facade delegates this provider-specific validation.
