# Claude Agent

`ClaudeAgent` is the provider-qualified concrete Agent (formerly `ClaudeRunner`). It inherits the [abstract lifecycle](../base/README.md).
The implementation is in `agent.py`; folder and object renaming do not
remove its whole-pipeline overrides.

A container opens and closes per turn. Output correction resumes the native session in a new turn scope with correction tools disabled.

| Method vocabulary | Provider contract |
| --- | --- |
| `runtime_binding()` | Public provider/runtime identity metadata; never credentials. |
| `model_catalog()` | Native model/effort discovery without a model turn. |
| `preflight()` | Check configured readiness/isolation; do not dispatch work. |
| `resume(...)` | Continue only an admitted existing provider/session binding. |
| `recover_interrupted(record)` | Reconcile exact recorded resources, without replaying execution. |
| `_execute(...)` | Protected provider hook, currently a pipeline override awaiting consolidation. |

Model Refresh, startup catalogue warming and Python preflight can all mirror the
local login before their native control request. Their stage policies can exceed
the graph's 75-second catalogue wait or a concurrent request's 65-second wait;
caller timeout does not cancel discovery. See the authentication adapter's
[timing and UI constraints](auth/README.md#discovery-preflight-and-startup-timing).

Native `activity/` and authentication under `auth/` (where implemented) belong
to this provider. `settings.py` owns protocol pins/configuration; `models.py`
owns structured values where present. No empty auth/model modules are required
for symmetry. Provider-independent secure storage, grants and Docker mechanics
retain their shared owners. Sibling provider imports are forbidden.

Start/resume/status/cancel use the base contract. The interface must explicitly
report unsupported capabilities and preserve unknown usage or partial evidence.
Successful execution, capture completeness and cleanup confirmation remain
separate facts. Existing stable error codes and persisted records do not change
with the Python object name.
