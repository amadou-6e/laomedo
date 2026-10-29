# Opencode Agent

`OpenCodeAgent` is the provider-qualified concrete Agent; the relocated class is still
named `OpenCodeRunner` until integration. It inherits the [abstract lifecycle](../base/README.md).
The implementation currently remains in `runner.py`; folder relocation does not
remove its whole-pipeline overrides.

The controller and broker span an attempt. Native history export follows confirmed closure and precedes the final freeze. Output requirements are currently unsupported.

| Method vocabulary | Provider contract |
| --- | --- |
| `runtime_binding()` | Public provider/runtime identity metadata; never credentials. |
| `model_catalog()` | Native model/effort discovery without a model turn. |
| `preflight()` | Check configured readiness/isolation; do not dispatch work. |
| `resume(...)` | Continue only an admitted existing provider/session binding. |
| `recover_interrupted(record)` | Reconcile exact recorded resources, without replaying execution. |
| `_execute(...)` | Protected provider hook, currently a pipeline override awaiting consolidation. |

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
