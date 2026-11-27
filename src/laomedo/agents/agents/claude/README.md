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

Model discovery and execution use the explicitly authenticated dedicated profile.
`ClaudeCredentialProvider.prepare` checks saved-connection admission without
reading or copying host login files. Native login and refresh belong to that
connection. `_prepare_credentials` is the shared pre-dispatch admission hook.
The runtime cleanup reserve remains in `settings.py`; no host-login mirror
package, flags, writer or error codes are supported.

Native `activity/` and credential admission in `credentials.py` belong
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

## Native assistant commands

`ClaudeCommands` in `commands.py` owns the observed catalog projection, exact
handler/image revision and no-argument `/compact`, `/usage`, `/context` and `/mcp`
policies. Read-only control views require actual native advertisement; terminal
commands omitted by the adapter remain unavailable. `admit()` refuses
unobserved commands, changed catalogs and contexts with pinned skills/custom
commands. `result()` requires root-session native compaction completion and a
terminal ACP response. `ClaudeCommandResult` in `models.py` retains that native
identity separately from model turns; it never supplies an invented answer or
usage. `ClaudeAgent` publishes the catalog through the existing run Status and
routes approved commands through its existing resume, cleanup and snapshot path.
`control_result()` requires root-session `local_command_output` identity and a
terminal ACP response, rejects native failures and reported model output, and
returns `ClaudeControlResult` with the actual ACP view text. It does not infer
success from prose, produce usage or label a control view as compaction. Live
provider acceptance is required separately from unit receipt-validation tests.

## Saved account connections

`quota.py` owns `ClaudeSubscriptionQuota.read()`: validate the selected saved
account, send only native initialize and `get_usage` with `skip_behaviors`, and
project subscription windows after exact controller cleanup. It never submits a
user message, scans transcripts, exports credentials or substitutes API costs.
The pinned CLI's experimental response is bounded and fails closed on unsupported
structure. Five-hour/week windows and scoped weekly buckets retain their native
percentages and reset times; extra-usage billing is not subscription allowance.

`connection.py` is the provider boundary. ClaudeConnection owns official-client begin/details/submit/cancel, native identity verification, exact labelled profile custody, orphan reconciliation and cleanup. ClaudeNativeProfile, ClaudeAccountIdentity and ClaudeLoginAttempt belong to models.py; its native cleanup budget belongs to settings.py. The shared Agent connection service owns admission/index fencing; host storage and profile authorization remain separate.

`ClaudeConnection.summary()` checks saved profile custody only; it never starts a
native client or revalidates OAuth while listing accounts. Native account checks
belong to admitted catalog, quota and execution operations.

ClaudeCommands.builtin_skills reads the root native SDK init skills list in isolated built-in-only sessions. Discovery retains this session binding and includes the observed skill set in the catalog revision; absent evidence never creates a skill.

The pinned adapter forwards SDK builtin markers. ClaudeCommands.skill_reason intersects those markers with the root init skill list and the capability table; expansion_receipt requires the native canonical slash-expansion marker. Admitted skill turns use ordinary native model completion, activity and usage, never local-control or compaction receipts. Personal skill/plugin sync is disabled in the invocation settings.

`quota.py` owns the claude implementation of `BaseSubscriptionQuota.read()`. The Agent exposes it through the optional `quota` property; callers use the shared contract. Native protocol, credential and teardown ownership is preserved.
