# Abstract Agent lifecycle

## Model discovery boundary

`base.py` declares `BaseModelCatalog.list_models(refresh=False) -> ModelCatalog`.
`models.py` defines `ModelCatalog` and `ModelOption`. Laomedo consumes this typed
result; each provider owns discovery, authentication, caching and exact cleanup.
`snapshot()` observes the last catalog without discovery, and `wait_until_idle()`
observes discovery completion without declaring readiness or success.

```python
from laomedo.agents.agents.base.base import BaseModelCatalog

def show_models(catalog: BaseModelCatalog):
    model_catalog = catalog.list_models()
    for model in model_catalog.models:
        print(model.id, model.display_name, model.reasoning_efforts)
```

| Value | Meaning |
| --- | --- |
| `ModelOption.id` | Exact provider selection ID; never a synthesized display name. |
| `display_name` | Provider-reported label, or `None` when unavailable. |
| `reasoning_efforts` | Supported execution-setting IDs. The existing `"default"` sentinel means omit an override; it does not establish a native default. |
| `default_reasoning_effort` | Explicitly reported default, or `None`; never the first available choice. |
| `resolved_model` | Reported native model behind an alias, when available. |
| `ModelCatalog.default_model_id` | Explicitly reported default selection ID, or `None`. |

Provider normalization retains Claude picker labels and resolved IDs, Codex
reported labels/defaults, and OpenCode reported labels. Unselected provider
metadata stays inside the provider. Catalog methods never submit a model prompt.

`ModelOption.from_payload()` and `ModelCatalog.from_payload()` translate the
existing provider-owned discovery records into canonical values. Their
`to_payload(include_model_names=...)` projection is the explicit existing HTTP boundary: `/v1/models`
keeps `id`/`efforts`, Claude `name`/`resolved_model`, and current catalog metadata.
New Python-only labels/defaults do not silently change that wire format.
Cached values and returned catalogs must be detached, including reasoning lists.

Claude retains shared in-flight refresh and stale observation for admission;
Codex retains serialized TTL discovery; OpenCode retains runner exclusion,
authentication checks and cleanup-before-publication. Failures must not replace
a prior successful cache. Readiness remains the separate existing Agent check.

`agent.py` defines abstract `BaseAgent`. It owns common run admission, file-backed records, request identity,
workspace freezing and artifact selection. It composes provider execution hooks;
it must not import concrete providers or their credential implementations.

`models.py` defines canonical `RuntimeBinding` and `CredentialBinding` values.
These are public identity metadata, never login material. `settings.py` owns
shared bounds. `acp/` owns protocol communication; native policy stays local.

## Agent interaction

`BaseAgent` declares the complete run-oriented interaction methods: `start`,
`start_async`, `resume`, `status`, `cancel` and `lookup_request`. Providers use
shared durable admission and observations; their resume implementations retain
native binding checks. `start_async` is a background-thread method, not a
coroutine. Requests and returned full records keep their current dictionary
payloads. Cancellation request and final confirmation remain distinct.

`resume` explicitly declares run/task, expected snapshot hash/thread ID,
model/effort, optional activity capture ID and optional run timeout. Claude
supports timeout overrides; Codex/OpenCode reject a non-None override before
native dispatch in fresh/resume paths, including HTTP admission. No public
session object or close method bypasses provider finalization. See the
[full contract and examples](../../../../../docs/architecture/agent-interaction.md).

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

## Shared Docker handling

`laomedo/docker.py` defines concrete `DockerRuntime`, the shared owner of
native client construction, session/job/command dispatch and receipt recovery.
See [container requirements and method ownership](../../../../../docs/architecture/provider-boundaries.md).
`client()` scopes a connection; `connect()` supports existing explicit cleanup
order. `run_job()` owns a client; `execute_job(client, job)` borrows one.
`session()` scopes a native interactive session; `start_session()` and
`close_session()` support persistent executor ownership. `run_command()` executes
inside an exact container. `recover()` owns a client; `recover_receipts()` borrows
one and never broadens the caller-selected receipts. SDK models stay canonical.

Providers retain image/volume policy, immutable launch configuration, native
readiness, credential phases, broker/lease coordination and stable error mapping.
They do not construct Docker clients or dispatch jobs/sessions/recovery directly.
ACP requests container closure through this module before reader disconnect;
repeated closure remains owned and cached by native py-docker Session.
An architecture regression scans all Agent sources for lifecycle bypasses.

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

`models.py` also owns private values, not only public bindings. `FailureObservation`
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

The catalog declares `include_model_names` for the existing HTTP projection.
Claude enables native display/alias names; the shared model never selects a
provider by name. This serialization policy does not change typed discovery.

## Activity boundary

`BaseAgent.read_activity(run_id, attempt_id, *, after=0, limit=100)` is abstract.
Providers return shared `ActivityPage` values with stable common records and a
revisioned display snapshot. Native interpretation stays internal; callers do not
supply another projector. See [the exact contract](../../../../../docs/architecture/activity-interface.md).
