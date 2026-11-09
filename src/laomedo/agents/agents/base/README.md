# Abstract Agent lifecycle

`agent.py` defines abstract `BaseAgent`. It owns common run admission, file-backed records, request identity,
workspace freezing and artifact selection. It composes provider execution hooks;
it must not import concrete providers or their credential implementations.

`models/runtime.py` and `models/credentials.py` define canonical runtime and credential bindings.
These are public identity metadata, never login material. `settings.py` owns
shared bounds. `acp/` owns protocol communication; native policy stays local.

## Target interface inspection (#277)

Import provider-facing contracts from `laomedo.agents.agents.base`. The package
initializer deliberately exports the target base classes and their support protocols.
Definitions live in concern files directly in this directory: invocation.py,
runtime.py, resources.py, credentials.py, commands.py, catalog.py and activity.py.
There is no second base/ folder. agent.py owns BaseAgent; docker.py owns the
shared concrete AgentDockerMechanism. Internal concern/model imports use defining
modules to avoid depending on the public aggregator during initialization.
`BaseAgent` remains defined in `agent.py`; it is not duplicated here. Target
Request/result values live in `models/` and are host-side values, not new wire
or persisted schemas. Journal operations use separate frozen operation models with named fields;
provider extensions cannot override shared record state. Container builders return
native specifications for shared allocation; non-Docker builders return owned
resources. Each plan has exactly one launch-phase controller.

| Target ABC | Required operations | Owner / boundary |
| --- | --- | --- |
| `BaseAgentRunner` | `open_activity_attempt`, `run` | Native execution for one admitted invocation |
| `BaseAgentRuntime` | `prepare`, `launch`, `run_job`, `controller_stream`, `close_controller`, `shutdown`; plan/error hooks | Shared Docker scope with provider policy |
| `BaseInvocationJournal` | Ownership, native binding, dispatch, turns, lease, publication, identity, correction, cleanup, evidence writes | Agent-owned durable persistence |
| `BasePostFreezeSettlement` | `settle`, `abort` | Supervision surviving any attempt outcome |
| `BaseCredentialProvider` | `admit` | Native credential admission |
| `BaseCommandExecutor` | `execute`, `request_cancel`, `shutdown` | Claude/OpenCode isolated workers |
| `BaseModelCatalog` | `discover` | Zero-turn native discovery |
| `BaseActivityProjector` | `accepts`, `project` | Read-time Activity interpretation |
| `BaseRuntimeResource` | `binding`, `close` | One runtime-plan allocation |

`ControllerStream`, `StopContext`, `StopSource` and builder callables are structural protocols,
not additional provider ABCs. `StopSignal`, `AgentDockerMechanism`,
`AgentProviderRegistry`, `CodexExecServer` and `AcpSession` are concrete roles,
so this inspection step does not invent abstract counterparts for them.

The providers still import the interim contracts in `interim.py`. No provider is
switched to these target ABCs in this inspection checkpoint. During migration,
provider authors import public contracts through the package; the interim contracts
and their retired operations will be removed, without forwarding aliases.
Runtime methods are abstract here so their intended obligations can be inspected;
the subsequent runtime implementation must share Docker mechanisms rather than
copy those methods into each provider.

## Shared Docker mechanisms (#277 checkpoint)

`docker.py` defines concrete `AgentDockerMechanism`. `client()` owns one
py-docker client context; `run_job()` collects one typed native job with unchanged
cancellation/deadline/cleanup bounds; `recover()` reconciles exact receipts using
the selected native job or session service. Each call owns its client, so worker
threads and recovery do not borrow an attempt's creator-thread session.
The mechanism snapshots supplied host environment overrides and accepts native
connection settings. Callers pin an already selected endpoint where available;
initial daemon discovery retains py-docker's existing selection behavior.
Provider code retains spec construction, admission and stable failure mapping.
This checkpoint does not yet move controller scope ownership into the shared
runtime: the reviewed target is recorded in issue #277 and its canonical design.

| Interface / vocabulary | Contract and effects |
| --- | --- |
| `start(request)` / `start_async(request)` | Admit a fresh run; persist identity before dispatch. Async acknowledgement is not completion. |
| `resume(run_id, task, **binding)` | Abstract provider operation on an existing identity; never silently create a new run. |
| `status(run_id)` | Read the retained record; does not dispatch work. |
| `lookup_request(request_id)` | Reconcile a durable client request; reject absent or conflicting identity. |
| `cancel(run_id)` | Request cancellation; confirmation and exact resource cleanup remain separate outcomes. |
| `model_catalog()` / `editor_model_catalog()` | Discover current metadata without a user/model turn. |
| `preflight()` | Abstract readiness check; not proof of successful execution. |
| `select_artifacts(run_id, selection)` | Select retained files under the artifact contract. |
| `publish(...)` | Delegate to an explicitly configured publication controller; does not own GitHub authorization. |

Protected extension points are `runtime_binding`, `recover_interrupted`,
`prepare_resume`, `_execute` and `_mirror_host_login`. Constructor recovery can
run before concrete initialization completes. Keep this ordering explicit.
Private helpers (`_prepare`, `_materialize`, `_freeze_workspace`, `_run_dir`)
are not application entrypoints. File-backed records and persisted schemas are
owned by this lifecycle.

Failures use the single [RunnerError](../../errors.py) hierarchy and stable codes.
Uncertain remote execution must not become an automatic retry. Normal Agent
execution has no verification quota or experiment admission hook.
## Structured preparation records

`PreparedRunRecord` in `models.py` constructs the initial durable run value.
`PreparedWorkspaceState` groups source/effective hashes, baseline and workspace
mode. `RuntimeBinding` remains the canonical provider binding; `AgentSkillBinding`
groups installed skill identity and byte evidence. `for_preparation()` derives
initial state after existing admission; `to_record()` preserves the persisted flat
JSON record, including explicit nulls and an omitted absent `github_scope`.

Provider execution, cancellation, recovery and historical readers still own the
existing mutable dictionary lifecycle. The preparation model is a writer, not a strict
reader for later provider-specific extensions. It performs no filesystem or model
effects. Native/raw records are not silently coerced into a closed schema.

## Private failure observations

`models/failures.py` owns private values, not only public bindings. `FailureObservation`
contains allowlisted stage/code/SDK metadata; `AttemptFailureRecord` groups the
first failure, optional cleanup failure, final category and a qualified cleanup
fact. `from_*` constructs trusted observations and `to_record()` projects private
JSON. Atomic `_json` writes `diagnostics/<attempt-id>.json` after normal
attempt/run writes. These observations are private diagnostic records.
Diagnostic errors never replace execution errors or prevent lock release.
The existing `BaseAgent._retain_attempt_failure` method owns the shared guarded
construction and atomic write. Providers supply already observed primary/cleanup
facts and their own cleanup domain; the base does not inspect lease or Docker
objects. Provider finalizers keep unconditional release of their locks/maps.

`cleanup_source=lease_result` describes only the exact leased resource's result;
`opencode_owned_resources` describes that backend's complete allocated resource
set after broker drain. Neither asserts global cleanup. A true private cleanup
fact does not override a public fail-closed run status. SDK metadata is captured
only from exact trusted exception classes and fixed code/operation allowlists;
messages, receipts, owner labels and credentials are excluded.

SDK privacy literals follow the exact declared `py-docker` revision. Its
`CreateNotSentDeadlineError` is a distinct trusted class with the existing
`docker_deadline_exceeded` code; a generic deadline does not establish that no
create was sent. Unknown subclasses and operation strings remain omitted.

## Contract concern index

| Module | Objects | Responsibility |
| --- | --- | --- |
| [invocation.py](invocation.py) | `BaseAgentRunner`, `BaseInvocationJournal`, `BasePostFreezeSettlement`; stop protocols | Native execution, durable write port, surviving supervision |
| [runtime.py](runtime.py) | `BaseAgentRuntime` | Shared resource lifetime with provider plan/error hooks |
| [resources.py](resources.py) | `BaseRuntimeResource`, `ControllerStream`, builder protocols | Exact resource closure and borrowed I/O; container builders return specs |
| [credentials.py](credentials.py) | `BaseCredentialProvider` | Admit native credentials without universal borrowing/release |
| [commands.py](commands.py) | `BaseCommandExecutor` | Isolated worker admission, cancellation and drain |
| [catalog.py](catalog.py) | `BaseModelCatalog` | Zero-turn discovery |
| [activity.py](activity.py) | `BaseActivityProjector` | Read-time native evidence interpretation |
| [interim.py](interim.py) | Current live provider ABCs | Temporary implementation contracts until #277 migration |

These are the target declarations for user inspection, not migrated provider
implementations. `interim.py` retains its current behavior and remains the
production guard's selected contract owner; it is not a compatibility forwarder.
Delete it when the actual providers and callers use the target contracts.

`BaseAgent` stays in [agent.py](agent.py). Shared concrete Docker code stays
in [docker.py](docker.py). Target method docstrings define admitted inputs,
failure outcomes and lifecycle order. The existing interface guard remains red on
unresolved provider runtime methods; this layout does not exempt them.

## Invocation nomenclature

An invocation is one admitted provider execution: it can contain multiple native
model/tool turns and remains distinct from the host run and saved conversation.
The defining concern is invocation.py. BaseAgentRunner.run takes InvocationRequest
and returns InvocationResult; InvocationContext carries the host context.
BaseInvocationJournal owns durable writes, not execution-state checkpoint restoration.

Persisted attempt_id and activity-attempt records keep their established schemas
and stable codes. open_activity_attempt names that existing activity record boundary.
StopContext still combines requesting and observing; it must not be called a
read-only cancellation token. ContainerBuilder/OwnedResourceBuilder remain an
unresolved construction/allocation design concern, not repaired by these renames.


## Provider-authoring experience

Public import: from laomedo.agents.agents.base import BaseAgent, BaseAgentRunner,
BaseAgentRuntime. Defining a subclass alone starts no service or task. BaseAgent
still requires provider-specific execution/readiness/resume hooks and undeclared
catalogue/credential class attributes. BaseAgentRunner still requires admitted
request, journal and stop collaborators and is not yet wired into shared Agent
execution. The registry currently admits only the existing three providers.

The canonical [provider-authoring story](https://github.com/amadou-6e/specs/blob/267ab0c1673bac9af564bfb5c07cd75e725e8c9d/projects/laomedo/subsystems/agent-execution/design/provider-authoring.md)
records that actual experience and the intended journey. This layout/export
checkpoint does not claim a complete one-class provider integration.
