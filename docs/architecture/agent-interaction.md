# Agent interaction: proposed public contract

Draft for #277, not an implemented or approved interface. Source baseline:
`08d6864c050a90f1dbea7d3c4ee71974f652c7ff`. The first public session-object
proposal received REVISE. This revision is fully unreviewed ? reviewer pending:
the same Claude session refused its next request, reporting a reset at 19:20
Europe/Berlin on 2026-11-10. The preceding catalog/readiness approval stands.

## One public abstract class

Use the existing Python ABC `BaseAgent`. Every provider subclasses it. Keep
native sessions internal; callers do not construct a second session object.
Shared lifecycle methods have shared implementations. Providers implement the
native execution and resume checks; they do not reimplement shared admission.

The interaction portion of the target declaration is:

```python
class BaseAgent(ABC):
    def start(self, request: dict) -> dict:
        """Prepare a fresh run and wait for execution/finalization to return."""

    def start_async(
        self, request: dict, *, response_gate: threading.Event | None = None
    ) -> dict:
        """Persist fresh-request admission, then execute in the background."""

    @abstractmethod
    def resume(
        self,
        run_id: str,
        task: str,
        *,
        expected_post_run_hash: str,
        expected_thread_id: str,
        model: str,
        effort: str,
        activity_attempt_id: str | None = None,
        run_timeout_seconds: int | None = None,
    ) -> dict:
        """Verify the retained binding, then execute another turn of that run."""

    def status(self, run_id: str) -> dict:
        """Read the current retained record without executing anything."""

    def cancel(self, run_id: str) -> dict:
        """Request cancellation and return current facts, not promised termination."""

    def lookup_request(self, request_id: str) -> dict:
        """Resolve uncertain acceptance of an idempotent fresh request."""
```

These signatures describe the target, not replacement bodies. In particular,
resume signatures currently differ and still need migration. The existing
`start_async` name means a background thread, not an awaitable coroutine.
`response_gate` is the existing HTTP acknowledgement coordination mechanism,
not a provider-supplied dependency. Ordinary Python callers omit it.

This is an interaction excerpt, not the entire BaseAgent definition. Existing
abstract provider identity, runtime_binding, recover_interrupted, readiness and
_execute responsibilities remain on that same discoverable class. Do not add
another mandatory runner/session/factory object to make this API callable.

## Preserve the payload before introducing more models

For this stage, keep the existing request dictionaries and complete returned
run records. They already carry typed domain values at their owning boundaries.
Do not create incomplete StartRunRequest/RunStatus models solely to make the
signatures look typed. Exact record fields, provider extensions, omitted values
and machine error categories must survive HTTP and persistence unchanged.

The discarded typed sketch had a concrete unresolved problem: RunStatus would
omit fields required in current HTTP responses. Reconstructing a record from its
model_dump would lose data; exposing a second raw-record API or making the host
call private provider methods would hide the issue rather than resolve it.
A later typed-request/record migration needs its own complete field inventory
and explicit wire projections; it is not required to align method ownership now.

Existing AgentRequest is an HTTP endpoint/method/body model; RunnerStatusRecord
is a permissive join observation; PreparedRunRecord constructs initial durable
state. None is a substitute for the complete interaction request or current
persisted lifecycle record.

## What a caller does

Fresh execution with live observation or cancellation:

```python
agent = CodexAgent(state, registry, source, lease_service=lease)
accepted = agent.start_async({
    "request_id": str(uuid4()),
    "task": "Explain this repository",
    "model": "gpt-6.1-sol",
    "effort": "low",
})
observed = agent.status(accepted["run_id"])
# If the application decides to cancel, from the owning service process:
observed = agent.cancel(accepted["run_id"])
# Read again later; cancellation acceptance is not cleanup confirmation.
observed = agent.status(accepted["run_id"])
```

A separate successful execution and resume:

```python
completed = agent.start({
    "task": "Read the repository",
    "model": "gpt-6.1-sol",
    "effort": "low",
})
if completed["status"] == "completed":
    resumed = agent.resume(
        completed["run_id"],
        "Explain the main entry point",
        expected_post_run_hash=completed["post_run_hash"],
        expected_thread_id=completed["thread_id"],
        model=completed["requested_model"],
        effort=completed["requested_effort"],
    )
```

A missing native thread or snapshot must refuse resume, not create a fresh run.
These examples illustrate the target/common call shape; their presence is not
new live integration evidence. A blocking resume must run in an application
worker if the same application also needs to observe or cancel it. Do not invent
an async-resume idempotency protocol without defining its persistence and races.

## Required behavior

| Operation | Shared ownership and observed outcome |
| --- | --- |
| start | Provider admission, shared workspace/skill/artifact/authorization preparation and durable record precede native dispatch. It returns the record after the execution path returns, or preserves existing exceptions. |
| start_async | Requires request_id. Existing exact body hash and duplicate/conflict handling stay unchanged, including unknown keys, omitted defaults and legacy skill_ref versus skill_refs. Acknowledgement is not completion. The host owns response-gate release. |
| resume | Same run_id, another native turn/capture. Provider checks completed state, thread/hash/model/effort and its full runtime/credential binding before dispatch. No new _prepare, workspace or run is silently created. |
| status | Reads retained facts. A completed native turn is not necessarily a finalized host run. Preserve attempt_finished, unknown/failed/interrupted states and missing values. |
| cancel | Prepared work can be cancelled before launch. Active work receives a request; cancel_requested and cancel_confirmed remain separate. Preserve foreign-process refusal and existing provider-specific repeated/terminal cancel behavior. |
| lookup_request | Reconcile an existing asynchronous fresh request; never use it as permission to replay an uncertain model turn. |

Trusted construction supplies source workspace, stores, image/profile,
credentials, leases, Git mode and publication/mediation services. Requests
cannot replace these with arbitrary paths or grants. Existing fresh request
fields remain task, model, effort, skill references, artifact references,
handoff, opaque GitHub authorization reference, output requirements/retries
and the currently supported provider-specific timeout field.

## Provider differences that stay explicit

| Provider | Resume admission | Finalization order that must remain intact |
| --- | --- | --- |
| Claude | Completed thread/hash/model/effort plus runtime version, image/profile/config and permission-grant checks. Validated per-turn timeout override. | Native ACP communication owns its teardown; successful execution verifies skills/freezes, then final facts include controller/descendant cleanup and mediation uncertainty. |
| Codex | Completed thread/hash/model/effort; workspace/protected mounts; profile/Git mode/execution mode/image/version/config. App-owned auth also binds runner instance and credential identity. | Native shutdown precedes successful snapshot freeze; later lease/publication settlement remains independently observed. |
| OpenCode | Provider model/effort rules, completed thread/hash/version, workspace/protected mounts and pinned skills. | Backend shutdown precedes native history reading/retention, then successful snapshot and telemetry/attempt settlement. Cleanup uncertainty can change the outcome. Production composition remains blocked. |

Do not standardize these by moving cleanup into a public close method. Introduce
no new model-turn cap: _reserve_turn is diagnostic accounting, not an execution
authorization or capacity gate.

The common optional run_timeout_seconds argument needs a selected unsupported-
provider policy before implementation. Recommended target: None retains existing
behavior; a non-None override is supported by Claude only and is refused before
dispatch elsewhere. Today's HTTP handling of ignored fields must not change
accidentally as a side effect; wire migration must be an explicit decision.
OpenCode output requirements remain unsupported. This design does not promise
new capabilities just because a method signature is common.

## Activity is a separate boundary

Do not add AgentEvent(kind=str) or attach lifetime control to a prompt iterator.
Existing Activity uses run/capture identity, separate native and OTLP line
cursors and bounded reads. Preserve those identities. A future common Activity
interface can observe execution independently of this interaction interface.
Stopping observation must not cancel a turn or close native resources.

Native turn/completed is not host finalization. The latest record, attempt
closure and resource/cleanup observations remain distinct. This draft does not
claim live activity streaming has been aligned or that an Activity API exists
merely because the underlying feed functions exist.

## Before implementation and completion

- Reviewer must verify the actual provider execution/resume/finalization bodies,
  not only method lists; preceding design review did not read all those bodies.
- Settle timeout refusal versus current wire behavior explicitly. Do not silently
  change accepted payloads, request hashes or persisted schemas.
- Declare every public common method and its actual parameters on BaseAgent;
  migrate provider implementations and external callers together.
- Preserve current provider-specific failure categories, finalization and
  cancellation facts. Do not turn unknown into success or cleanup confirmation.
- Check duplicate/conflicting async requests, uncertain acknowledgements,
  changed workspace/runtime/auth resume refusal, prepared/active/foreign-process
  cancellation, cleanup failure and observation during finalization.
- Validate HTTP full-field round trips, field presence and unknown payload keys;
  no saved personal graph compatibility layer is required.
- Use real execution/resume/cancel acceptance for each provider or state its
  exact blocker. Existing evidence does not validate an unimplemented interface.
- The existing 19 runtime-interface violations need their own call inventory and
  real internal alignment. Merely approving this public declaration does not
  resolve them; no unused ABC declarations, aliases or guard exemptions.
