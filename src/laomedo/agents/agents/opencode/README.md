# Opencode Agent

`OpenCodeAgent` is the provider-qualified concrete Agent (formerly `OpenCodeRunner`). It inherits the [abstract lifecycle](../base/README.md).
The implementation is in `agent.py`; folder and object renaming do not
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

`OpenCodeConfig` in `models.py` groups permission rules, broker port and the
private capability. `to_config()` projects the native controller configuration;
normal dumps/reprs exclude that capability. Trusted host routing and startup
extensions retain their existing validation and run after this base projection.
The `http/` package owns `BrokerHttpServer` and `BrokerRequestHandler` with an
explicit broker reference; `do_POST` is the framework callback, not a new Agent API.

Start/resume/status/cancel use the base contract. The interface must explicitly
report unsupported capabilities and preserve unknown usage or partial evidence.
Successful execution, capture completeness and cleanup confirmation remain
separate facts. Existing stable error codes and persisted records do not change
with the Python object name.

## Runtime identity value

`OpenCodeRuntimeIdentity` groups the controller/worker images, profile identity,
CLI version and existing keyed credential fingerprint. `IsolatedOpenCode` keeps
that object internally; its `runtime_identity` property calls `to_payload()` only
for the existing provider fingerprint boundary. Profile identity read from legacy
JSON retains its admitted shape. The fingerprint is metadata, never a login token.

## Exact resource closure (implementation target)

The backend and broker register exact allocated receipt paths before dispatch.
`close()` stops admission, closes the controller, drains the broker, reconciles
those paths through the SDK, then closes the Docker client. Partial construction
has optional handles and no invented resources. An unresolved drain/receipt/cleanup
keeps termination unverified; no job or model retry occurs. Existing startup
receipt scans remain unchanged, including their shared-directory lock limitation.

`models()` maps SDK cleanup uncertainty to `opencode_container_cleanup_unverified`
before its generic startup mapping, preserving safe SDK metadata. In-run failures
use the shared private attempt snapshot after normal writes; metadata discovery
has no attempt or new store and retains its existing HTTP code boundary. A true
`opencode_owned_resources` cleanup fact requires all allocated catalog/controller/
worker resources, not controller absence alone. It never accepts a failed run.
