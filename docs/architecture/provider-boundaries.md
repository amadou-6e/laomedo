# Provider boundaries and shared containers

This is the owner-selected direction for #277, replacing the unimplemented
runner/journal/resource-plan ABC proposal. Existing provider execution remains
in place while concrete shared mechanisms are extracted. Do not implement an
abstract role solely because a provider has a similarly named internal object.

| Boundary | What Laomedo consumes |
| --- | --- |
| Activity | Read history and translate native events into common activity. |
| Containers/resources | Prepare, launch, inspect and clean up owned resources. |
| Agent interaction | Start/resume sessions, prompt, stream results and cancel. |
| Model discovery/readiness | List models and report the readiness actually checked. |
| Recovery | Reconcile interrupted runs and clean up surviving owned resources. |

These are responsibilities, not five mandatory ABCs. Public contracts must be
justified by real shared callers. Provider configuration/identity connects these
boundaries; journaling, leases, publication and cancellation are host-supplied
services, not extra provider implementations. Their final composition API is
not designed yet. Existing live base classes remain until their callers migrate.

## Container ownership

`AgentDockerMechanism` in `agents/agents/base/runtime.py` delegates to py-docker.
It provides concrete client, session, job and exact-receipt delegation seams.
Only selected callers use them today; complete migration is a target.
Provider code supplies launch configuration, native readiness and resource order.
It retains existing error mapping and credentials checks. The target for a new provider is to reuse Docker lifecycle rather than subclass
it or implement another Docker client. Existing live runtime ABCs remain during
migration.

Interactive agent containers use a `ContainerSession`; finite command containers
use a `ContainerJob`. Both use native `ContainerSpec` and `StreamLimits`, not a
second Laomedo copy of those models. Session scope closure is distinct from ACP
disconnect, draining brokers/readers, and resolving leases. Preserve those
ordering requirements and report uncertainty; never infer whole-run cleanup from
one container's successful removal.

## Requirements for a provider container

1. Supply an explicit native specification: resolvable image (preserve admitted
   image pins), entrypoint/arguments, working directory, user, environment,
   network policy and mounts. Trusted host configuration owns these values;
   graph input must not choose arbitrary executables, mounts or secret sources.
2. Preserve isolation: credential-bearing processes and credential-free command
   workers have distinct mount/network policies. Do not put host credentials or
   a Docker socket in a worker merely to simplify execution. Secret values must
   not enter logs, diagnostics or serializable public configuration.
3. For an interactive agent, expose the configured bidirectional byte stream.
   Our current agents speak ACP over that stream; keep protocol output separate
   from diagnostics. Container launch alone does not establish ACP readiness,
   authentication, model availability or successful execution.
4. Supply explicit native stream/time bounds and a durable ownership receipt
   before dispatch. Keep endpoint selection pinned after admission and preserve
   exact-resource recovery. Missing or uncertain cleanup must remain a failure.
5. Close interactive sessions on their creator thread. Worker jobs own separate
   clients. Stop new worker admission and drain owned work before declaring its
   resource set cleaned. Attempt remaining cleanup even after one resource fails.
6. Persist native conversation state outside disposable container storage when
   resume requires it. Reconnect using the same native session identity; never
   silently replace resume with a fresh conversation.
7. Document prerequisites and native readiness checks. Verify start, protocol
   initialization, prompt/result, cancellation, resume and interrupted-resource
   recovery with the actual image before claiming provider acceptance. Unit
   tests of lifecycle delegation are supporting evidence only.

Different commands, mounts, worker topologies and lifetimes are configuration or
sequencing differences. They are not evidence for separate Docker mechanisms.
Anthropic documents multiple queries in one open ClaudeSDKClient in its
[session cookbook](https://platform.claude.com/cookbook/claude-agent-sdk-04-migrating-from-openai-agents-sdk).
That does not establish reuse for our pinned claude-agent-acp adapter, where
correction executions change tool/MCP configuration. Reuse remains unverified
for that adapter. This extraction preserves existing per-execution lifetimes;
changing them is a separate behavioral task.

## Remaining extraction work

Direct native calls still exist in Codex's split executor and admission paths,
OpenCode's catalogue and history reader, and Claude's authentication helpers.
Those paths must migrate with their actual endpoint/receipt/cleanup semantics.
The shared session context is a first delegation seam, not completed container
unification. AcpSession.close still closes the underlying native session before
SDK reader disconnect; its overlapping cleanup ownership is explicitly unresolved.
Do not remove that close until reader shutdown ordering is preserved.

## Completion checks

- [ ] All agent and worker container launch/close/recovery paths use shared
      mechanisms, with no provider-owned duplicate Docker lifecycle.
- [ ] Existing endpoint, image, deadline, output, receipt and error semantics hold.
- [ ] Partial startup, cancellation, uncertain cleanup and recovery are covered.
- [ ] Provider resource ordering and thread ownership are explicit.
- [ ] Real-image acceptance covers each supported provider; fixture tests alone
      do not check this box.

The initial session extraction does not complete this checklist or the five
boundary contracts. The earlier architecture review returned REVISE; replacement
implementation needs its own review.
