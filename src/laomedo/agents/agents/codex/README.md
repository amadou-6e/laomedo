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
