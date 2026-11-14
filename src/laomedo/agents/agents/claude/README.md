# Claude Agent

`ClaudeAgent` is the provider-qualified concrete Agent. It inherits the [abstract lifecycle](../base/README.md).
`agent.py` owns Claude preparation, execution and finalization alongside the
inherited lifecycle hooks.

Native Activity text and thinking blocks are assistant output only when their
receipt identifies an assistant message. The host-submitted prompt supplies the
user entry; native user echoes remain in raw evidence without a second display
entry. User-carried tool results still complete their corresponding tool calls.

A container opens and closes per turn. Output correction resumes the native session in a new turn scope with correction tools disabled.

| Method vocabulary | Provider contract |
| --- | --- |
| `runtime_binding()` | Public provider/runtime identity metadata; never credentials. |
| `model_catalog()` | Native model/effort discovery without a model turn. |
| `preflight()` | Check configured readiness/isolation; do not dispatch work. |
| `resume(...)` | Continue only an admitted existing provider/session binding. |
| `recover_interrupted(record)` | Reconcile exact recorded resources, without replaying execution. |
| `_execute(...)` | Protected provider hook implementing execution and finalization. |

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

## Workspace command boundary

`ClaudeCommandExecutor` in `executor.py` owns admitted local commands. Its
`ClaudeCommandTransport` in `http/commands.py` owns authenticated HTTP adaptation
and host mediation. `ClaudeRuntimePolicy` in `policy.py` owns launch/lease policy;
`ClaudeAgentRuntime` in `runtime.py` owns each exact turn session.

| Method | Contract |
| --- | --- |
| `ClaudeCommandExecutor.execute(request)` | Run a typed workspace command under the turn's policy and deadline; return native output and scoped cleanup evidence. |
| `ClaudeCommandTransport.mediate(value)` | Forward one scoped operation directly to the host mediator, bypassing proxies and refusing redirects. |
| `ClaudeCommandExecutor.shutdown()` | Stop owned command jobs and confirm their journal cleanup before releasing the workspace. |

An authoritative HTTP refusal remains a refusal. Redirects, server failures and
transport interruptions leave mediation unconfirmed and stop further commands;
the service never resends an operation. This transport policy does not establish
end-to-end native GitHub mediation readiness.
