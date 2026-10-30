# Codex Agent

`CodexAgent` is the provider-qualified concrete Agent (formerly `CodexRunner`). It inherits the [abstract lifecycle](../base/README.md).
The implementation is in `agent.py`; folder and object renaming do not
remove its whole-pipeline overrides.

A controller and optional executor span the attempt and output corrections. Native precheck and split-executor guards remain explicit.

| Method vocabulary | Provider contract |
| --- | --- |
| `runtime_binding()` | Public provider/runtime identity metadata; never credentials. |
| `model_catalog()` | Native model/effort discovery without a model turn. |
| `preflight()` | Check configured readiness/isolation; do not dispatch work. |
| `resume(...)` | Continue only an admitted existing provider/session binding. |
| `recover_interrupted(record)` | Reconcile exact recorded resources, without replaying execution. |
| `_execute(...)` | Protected provider hook, currently a pipeline override awaiting consolidation. |

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

## Failure finalization (implementation target)

Every noncompleted attempt, including early cancellation returns, retains a
private `AttemptFailureRecord` after ordinary run/attempt writes. Its first code
is `lease_service_lost` whenever supervision loss is set, never an inferred user
cancel. The first `LeaseLossObservation` (or unavailable reason) remains in the
exact private lease directory, correlated through existing ownership; no public
payload extension is introduced. Unknown dynamic codes are deliberately omitted.

The primary failure survives later close, snapshot and lease-finish failures.
`LeaseClient.result` retains an actual result before a lost-lease rejection.
Project it through `LeaseCleanupObservation`: no result means no cleanup fact,
not false. The sidecar's lease cleanup boolean covers only that leased resource.
The existing public fail-closed status/category wins even beside verified cleanup.
Fresh native answers, counters and completion never establish Resume success.
