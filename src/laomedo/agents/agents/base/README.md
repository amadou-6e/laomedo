# Abstract Agent lifecycle

`agent.py` defines abstract `BaseAgent` (formerly `Runner`). It owns common run admission, file-backed records, request identity,
workspace freezing and artifact selection. It composes provider execution hooks;
it must not import concrete providers or their credential implementations.

`models.py` defines canonical `RuntimeBinding` and `CredentialBinding` values.
These are public identity metadata, never login material. `settings.py` owns
shared bounds. `acp/` owns protocol communication; native policy stays local.

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
are not application entrypoints. RunStore extraction is still a target: current
file records and schemas remain unchanged during relocation.

Failures use the single [RunnerError](../../errors.py) hierarchy and stable codes.
Uncertain remote execution must not become an automatic retry. The existing
`_turn_available` hook imposes no production verification quota.
# Structured preparation records

`PreparedRunRecord` in `models.py` constructs the initial durable run value.
`PreparedWorkspaceState` groups source/effective hashes, baseline and workspace
mode. `RuntimeBinding` remains the canonical provider binding; `AgentSkillBinding`
groups installed skill identity and byte evidence. `for_preparation()` derives
initial state after existing admission; `to_record()` preserves the legacy flat
JSON record, including explicit nulls and an omitted absent `github_scope`.

Provider execution, cancellation, recovery and historical readers still own the
existing mutable dictionary lifecycle. The new model is a writer, not a strict
reader for later provider-specific extensions. It performs no filesystem or model
effects. Native/raw records are not silently coerced into a closed new schema.
