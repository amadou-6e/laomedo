# Provider boundaries and shared containers

This is the owner-selected direction for #277, replacing the unimplemented
runner/journal/resource-plan ABC proposal. Existing provider execution remains
in place while concrete shared mechanisms are extracted. Do not implement an
abstract role solely because a provider has a similarly named internal object.

| Boundary | What Laomedo consumes |
| --- | --- |
| Activity | Read history and translate native events into common activity. |
| Containers/resources | Prepare, launch, inspect and clean up owned resources. |
| Agent interaction | Start/resume runs, observe status and request cancellation. |
| Model discovery/readiness | List models and report the readiness actually checked. |
| Recovery | Reconcile interrupted runs and clean up surviving owned resources. |

These are responsibilities, not five mandatory ABCs. Public contracts must be
justified by real shared callers. Provider configuration/identity connects these
boundaries; journaling, leases, publication and cancellation are host-supplied
services, not extra provider implementations. Their final composition API is
not designed yet. Existing live base classes remain until their callers migrate.

## Model discovery

Laomedo calls the Python abstract `BaseModelCatalog.list_models(*, refresh=False)`
and receives `ModelCatalog`, containing `ModelOption` entries. These are defined
in `agents/agents/base/base.py` and `models.py`, and exported from that package.
Existing `ClaudeModelCatalog`, `CodexModelCatalog` and `OpenCodeModelCatalog`
implement the same method. Their Agents supply their native collaborators;
shared callers depend on the base contract rather than concrete catalog classes.

```python
from laomedo.agents.agents.base import BaseModelCatalog

def show_models(catalog: BaseModelCatalog):
    result = catalog.list_models()
    for model in result.models:
        print(model.id, model.display_name, model.reasoning_efforts)
```

Each option carries the exact selection ID, optional reported display name,
supported reasoning-setting IDs, optional reported default effort and optional
resolved native ID behind an alias. The catalog has an optional reported
`default_model_id`. Missing labels/defaults stay `None`: the first model or effort
is never selected implicitly. The existing `"default"` execution-setting sentinel
means omit an override, not proof of the native default. Discovery alone is not
authentication or execution-readiness attestation.

| Provider | Native discovery and normalization | Retained provider policy |
| --- | --- | --- |
| Claude | Initialize-only picker: alias, label, resolved native ID and effort choices; defaults remain unknown. | Shared in-flight refresh, TTL cache and stale observation for dispatch admission. |
| Codex | Paginated adapter model listing: ID, label, effort choices and explicit `isDefault` / `defaultReasoningEffort`. | Serialized TTL discovery, bounded pages, exact controller shutdown and receipt recovery. |
| OpenCode | Verbose native model records: provider-qualified ID and reported label; existing omission setting, defaults unknown. | Connected-provider validation, runner exclusion, auth freshness and cleanup before publishing/cache. |

Only normalized values cross this Python boundary. Native metadata remains in
its provider. `snapshot()` observes the last result without discovery;
`wait_until_idle()` observes completion, not success. Returned option lists are
detached from cache state. A failed refresh preserves the last successful cache.

The HTTP `/v1/models` response remains its current payload. Explicit
`ModelCatalog.to_payload(include_model_names=...)` projects `id`/`efforts`, Claude
`name`/`resolved_model` and existing catalog metadata. The new Python-only default
and label information does not silently change that external schema. Readiness
remains the existing, separate Agent boundary; this extraction does not add an
inference probe or broaden OpenCode production composition.

## Execution readiness

`BaseAgent.readiness() -> ReadinessObservation` is the Python abstract boundary.
The existing provider Agents implement it; no separate checker object is needed.
`preflight()` retains the native diagnostic payload and exception behavior.
Readiness performs that same zero-turn check and normalizes declared admission
failures into a result with `ready`, `reason`, `provider` and `scope`.

```python
from laomedo.agents.agents.base import BaseAgent

def show_readiness(agent: BaseAgent):
    result = agent.readiness()
    print(result.ready, result.reason, result.scope)
```

`ready=True` means the provider's stated execution prerequisite check passed at
that moment, not that a later turn will succeed. `False` means a known blocker;
`None` means execution remains unverified. Both False and None require a stable
reason code; presentation/recovery text stays in the shared error catalogue.
Unexpected programming errors propagate rather than masquerading as a blocker.
There is no cached readiness, inference request, retry or automatic login.
Constructor failures still occur before an Agent exists to query.

| Provider | Check performed | Successful result | Blocked result |
| --- | --- | --- | --- |
| Claude | Existing native subscription auth check, including the explicitly configured login mirror | True, scope `native_subscription_authentication` | False with the original admission error code |
| Codex | Existing ACP initialization and sandbox permission probes, followed by native cleanup | None, reason `authentication_not_verified`; these probes do not authenticate a session | False with the original admission/authentication error code |
| OpenCode | Existing transport configuration inspection; no backend startup | None, reason `opencode_transport_not_verified` | False, reason `opencode_isolated_transport_required` when no factory is configured |

`payload` retains detached native preflight details for existing explicit
consumers, including the CLI, but is excluded from generic model serialization
and representations. A diagnostic payload's `status=ready` never overrides the
provider's narrower typed conclusion. Cleanup errors cannot produce a ready
result. Process health and model discovery remain independent observations.

## Agent interaction

The public interaction owner is the existing Python abstract `BaseAgent`:
`start`, `start_async`, `resume`, `status`, `cancel` and `lookup_request`.
All providers declare the same resume parameters. Complete request/record
payloads and provider finalization stay intact; cancellation is an observation,
not guaranteed termination. Claude alone supports per-run timeout overrides;
Codex/OpenCode refuse non-None overrides before dispatch. See
[the complete contract and caller examples](agent-interaction.md).
This change does not align native runtime internals or the separate Activity API.

## Container ownership

`DockerRuntime` in `src/laomedo/docker.py` delegates to py-docker.
It provides concrete client, session, job and exact-receipt delegation seams.
Agent execution and independent host lease supervision use these concrete mechanisms.
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

## Unified Docker dispatch

Provider paths using the Python Docker SDK route client construction, interactive
launches, one-shot jobs, in-container commands and exact receipt recovery through
`DockerRuntime` in `src/laomedo/docker.py`.
This includes controller and worker execution, authentication/profile setup,
model discovery, OpenCode offline history, preflight, interrupted-run recovery
and independent lease-supervisor cleanup.
The architecture check scans every Laomedo source file for native Client imports
and direct SDK dispatch/recovery calls. It does not prove the absence of indirect
aliases or Docker CLI subprocesses.

Codex `activity/rollout_export.py` still launches three Docker CLI jobs for its
selected native history export. It uses local-only image lookup (`--pull=never`)
but does not use shared receipts or pin the daemon with `--host`. Outside Agents,
`work_graph/docker_stage.py` and host publication bundle staging/ownership also
retain their own Docker CLI operations. These paths remain migration work;
the current extraction is not complete consolidation of all Docker handling.

| Operation | Shared entry point | Ownership |
| --- | --- | --- |
| Scoped client | `client()` | Context closes the native client. |
| Long-lived client | `connect()` | Caller closes at its existing finalization point. |
| Finite worker/control job | `run_job(job)` | Own client per call, including worker threads. |
| Job on an existing client | `execute_job(client, job)` | Borrowed client remains open. |
| Scoped interactive container | `session(client, request)` | Context closes the exact native session. |
| Persistent executor | `start_session(client, request)` / `close_session(session)` | Explicit owner retains native cached cleanup failure. |
| Command in an existing container | `run_command(client, identity, command, limits)` | No container creation, replacement or retry. |
| Recovery | `recover(receipts)` / `recover_receipts(client, receipts)` | Exact selected receipts; stop on uncertainty. |
| Supervisor observation/removal | `inspect_reservation(client, reservation)` / `cleanup_reservation(client, reservation, watch_seconds=...)` | Original pinned daemon, exact labels, unchanged delayed-create watch. |

Native py-docker models remain canonical. Image resolution, volume labels,
inspection assertions and launch configuration remain provider policy using
services on the centrally constructed native client; no second SDK is built.
Provider-local finalization still coordinates brokers, reader threads, leases,
telemetry and native error mapping. This extraction does not merge those agent
concerns into Docker handling.

ACP requests native session closure through the shared implementation before
SDK reader disconnect. The enclosing session context also exits the same native
Session owner. Native idempotent close retains cached failure on repeated
requests; the protocol layer does not implement container termination itself.
Do not reorder this into disconnect-before-container-close: the blocking reader
must reach EOF before asyncio.run shuts down its executor.

## Automatic registered image acquisition

`docker/images.json` registers each provider image tag, Dockerfile, exact context
inputs and a zero-turn version command. Claude uses `docker/claude`, Codex uses
`docker/codex-acp`, and OpenCode uses `docker/opencode`. The OpenCode worker has
an independent tag built from the Codex context. Installed wheels include these
same inputs; image acquisition does not depend on a source checkout or cwd.

Before container startup, `DockerRuntime.ensure_image(client, image)` inspects the
selected daemon. Only Docker's explicit image-not-found response allows a build.
The runtime locks that daemon/tag, inspects again, snapshots only registered files,
and builds a temporary tag with Docker BuildKit. Docker CLI and BuildKit are
required. Building may download base layers and locked dependencies over the
network; model credentials and request-controlled paths or arguments are not
passed to the build. Registry authentication uses the user's normal Docker config.

The runtime verifies the built image with a finite, network-disabled version job,
then publishes its registered tag and returns the actual daemon image ID. Runs
use that ID. A recipe fingerprint covers the registration and context bytes.
An existing tag with a different fingerprint fails and requires explicit removal
before rebuilding; it is never silently replaced. Explicit caller-supplied image
IDs remain strict and are not relaxed to permit a rebuild.

Concurrent callers reuse the verified result. Build failure or interruption never
publishes the final tag. OS file locks release on process exit. CLI timeout or
cancellation terminates the owned local build processes; daemon-side build cache
or a staging tag can remain, so this does not claim daemon-wide cancellation.
Version-job cleanup uses the existing exact-receipt recovery mechanism.

`LAOMEDO_IMAGE_BUILD_SECONDS` (default 900) and
`LAOMEDO_IMAGE_VERIFY_SECONDS` (default 30) are separate from model-turn budgets.
Progress logging reports build steps without copying arbitrary build diagnostics.
Build or verification failures stop startup with `container_image_build_failed`.
Image lookup and explicit-pin failures retain their provider-specific codes.

## Open and unchanged

This extraction does not change persisted schemas, native identities, error
codes or recovery ordering. Recovery before concrete provider initialization,
credential timing, host-owned GitHub authorization, zero-turn discovery/cache
semantics, correction behavior and existing worker cancellation timing remain.
Preserve Codex post-freeze lease/publication settlement and OpenCode post-close
history ordering. Missing OpenCode production composition remains explicitly
blocked rather than supplied implicitly by this Docker change.

The earlier unresolved questions remain separately scoped: DESIGN-04 concerns
persisted `cancel_confirmed` meaning; DESIGN-09 concerns worker cancellation
timing; DESIGN-10 needs a Claude stream-JSON discovery specification ruling;
DESIGN-11 concerns correction policy. Withdrawing the abstract-object proposal
does not resolve or authorize behavioral changes to any of these questions.

## Completion checks

- [ ] All agent and worker container launch/close/recovery dispatch paths use
      shared mechanisms. Codex native rollout export still bypasses this owner.
      Native SDK image/volume/inspection policy stays explicit.
- [ ] Existing endpoint, image, deadline, output, receipt and error semantics hold.
- [ ] Partial startup, cancellation, uncertain cleanup and recovery are covered.
- [ ] Provider resource ordering and thread ownership are explicit.
- [ ] Real-image acceptance covers each supported provider; fixture tests alone
      do not check this box.

Unified Docker dispatch does not establish real-provider acceptance or complete
the other four boundary contracts. The shared SDK dispatch implementation was
reviewed separately from image acquisition. Neither review establishes full
provider acceptance or resolves the remaining CLI migrations and runtime contracts.

## Activity read boundary

Implemented on `BaseAgent.read_activity(run_id, attempt_id, *, after=0, limit=100)`.
All three providers return shared normalized pages; application capture retains
common records and a revisioned shared display snapshot. The former public
projector ABC and forwarding wrappers are retired. Existing saved native history
keeps a private read-only interpretation path. See [the complete method, data and
streaming contract](activity-interface.md). Claude approved the Activity code
and selected specification at `3778e2714`, then the full interface document.
Current-code fresh/resume/cancellation acceptance passes for Codex, Claude and
explicitly composed supported-route OpenCode. Claude approved the new harnesses
and supported their disclosed conclusions at exp c11976467..271f9058c; see the
Activity interface document for evidence and limits. All five GitHub checks pass
at68415e3dd, including the runtime contract guard. PR250 remains draft with
host-loss/daemon-wide cleanup and older broad-PR review gaps.

## Native runtime ownership

The former `BaseAgentRuntime`, `RuntimeLaunch` and unused runtime observation
wrappers are retired. No shared Laomedo caller consumed that nominal role; only
provider code used its divergent native methods. Providers construct their native
runtimes directly. Codex awaits native `close()`; OpenCode keeps its current
synchronous backend `close()` and `cancel()` factory protocol; Claude keeps its
creator-thread context manager. No external factory protocol or saved record
changes. Cleanup still precedes Codex freezing/cancellation confirmation and
OpenCode history retention. Shared Docker mechanics remain in `DockerRuntime`.
The contract guard continues covering every remaining declared role, with no
baseline or provider exceptions; retired classes/imports cannot return.

Claude approved this retirement's code delta `98d130bb9..acc9c41ae`, selected
specification and documentation, subject to this review-status update. Full Agent
suite: 693 tests pass, four skipped. Real Codex fresh/resume/cancellation passed
on that head. These scoped approvals do not cover later changes or establish host-loss or
whole-PR acceptance. Separate native-provider evidence and its review are
recorded above; installed-wheel CI corrections acc9c41ae..68415e3dd also received
implementation/documentation APPROVE.
