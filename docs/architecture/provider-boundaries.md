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
Its client, session, job and exact-receipt operations are shared concrete code.
Provider code supplies launch configuration, native readiness and resource order.
It retains existing error mapping and credentials checks. A new provider does
not subclass Docker lifecycle or implement a second Docker client.

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
Claude does not inherently require a new process/container per prompt: the SDK
supports multiple queries in one open client. This extraction initially preserves
our existing per-execution lifetimes; changing them is a separate behavioral task.

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
