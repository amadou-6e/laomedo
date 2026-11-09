# Abstract Agent lifecycle

`agent.py` defines abstract `BaseAgent`. It owns common run admission, file-backed records, request identity,
workspace freezing and artifact selection. It composes provider execution hooks;
it must not import concrete providers or their credential implementations.

`models.py` defines canonical `RuntimeBinding` and `CredentialBinding` values.
These are public identity metadata, never login material. `settings.py` owns
shared bounds. `acp/` owns protocol communication; native policy stays local.

## Shared Docker mechanisms (#277 checkpoint)

`runtime.py` defines concrete `AgentDockerMechanism`. `client()` owns one
py-docker client context; `run_job()` collects one typed native job with unchanged
cancellation/deadline/cleanup bounds; `recover()` reconciles exact receipts using
the selected native job or session service. Each call owns its client, so worker
threads and recovery do not borrow an attempt's creator-thread session.
The mechanism snapshots supplied host environment overrides and accepts native
connection settings. Callers pin an already selected endpoint where available;
initial daemon discovery retains py-docker's existing selection behavior.
Provider code retains spec construction, admission and stable failure mapping.
The unimplemented target ABCs have been withdrawn. See
[provider boundaries and container requirements](../../../../../docs/architecture/provider-boundaries.md).
`session(client, request)` owns one native session context on an explicitly
caller-owned client. It closes the session before returning control to outer
resource cleanup and preserves native exception/cleanup behavior. The caller
keeps client ownership so existing broker/worker/log cleanup order is unchanged.

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
