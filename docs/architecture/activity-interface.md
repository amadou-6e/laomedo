# Activity interface: minimal design recommendation

This supersedes the earlier reader/read_detail proposal for #277. No Activity
implementation has changed. After the owner's request to stop adding interface
objects, the existing Claude reviewer recommended retaining the existing
objects and adding none. That scoped design recommendation is approved by the
reviewer; full Activity implementation acceptance is not established.

## Necessary objects

| Layer | Existing object | Responsibility |
| --- | --- | --- |
| Provider extension | BaseActivityProjector | Convert retained provider receipts into ActivityProjection. |
| Application composition | agents/activity/projection.py: project | Select the stored provider's projector and return the existing wire payload. |
| Data | ActivityProjection | Shared envelope with native extensions and unknown values. |
| Internal persistence | ActivityStore | Owner/flow/node-scoped retained receipts, paging, binding and deduplication. |
| Internal observation | ActivityCapture | Follow runner feeds, retain observations and determine capture completeness. |

Do not add RunnerActivityReader, ActivityReader, ActivityStore.read_detail,
ActivityReadRequest, ActivityPage or a synthetic combined cursor. Do not require
a new BaseAgent activity method merely to duplicate existing application reads.
A runner method that removes host calls to _run_dir would be a separately scoped
encapsulation change, not the common provider activity interface.

## Actual provider interface

The existing class is defined in agents/agents/base/base.py. This is its current
contract, not a new class to implement alongside it:

```python
class BaseActivityProjector(ABC):
    usage_first_payload = False

    @classmethod
    @abstractmethod
    def accepts(cls, events) -> bool:
        """Recognize unqualified receipts for the existing internal fallback."""

    @abstractmethod
    def project(
        self, events, *, root_thread=None, model=None,
    ) -> ActivityProjection:
        """Convert accumulated retained observations to the shared envelope."""
```

Each provider currently implements both abstract methods. accepts is used by
legacy unqualified selection; stored provider identity is authoritative for app
reads. Making accepts optional is a separate decision. OpenCode's wrapper
converts its helper's dictionary to ActivityProjection; Claude and Codex return
that model through the shared normalized timeline implementation.

Input rows are the retained store shape: sequence, received_at, kind,
provenance and raw. The raw capture wrapper is shared, but the nested native
event remains provider-specific. Raw runner feed pages have a different shape
and cannot simply be passed to this method as complete invocation history.

## What is standardized, and what is still missing

ActivityProjection standardizes its top-level fields and application-owned
metadata. Missing usage/cost remains unknown. Its native-bearing lists/maps use
SkipValidation and retain provider extensions: turns, items, threads, telemetry,
diagnostics, usage snapshots/points and cost are not a fully enforced common
record schema. Do not describe the whole result as fully standardized activity.

If the owner wants fully provider-independent message/tool/usage records, the
next design work is defining those records and guarantees inside the existing
activity contract. Another reader class or method does not supply that missing
standardization. No new schema or capture migration is selected here.

## Source, retained copy and translation

The runner's private files supply capture-bounded native and OTLP observations.
ActivityCapture follows those independent cursors and writes an owner-scoped
retained copy to ActivityStore. SQLite receipt sequences are a third coordinate;
none of these cursors may be merged or substituted.

The application reads stored rows and invokes the existing project function:

```python
page = store.read(owner_id, flow_id, node_id, invocation_id, after=0, limit=100)
# For a full detail projection, the existing route collects bounded pages first.
activity = project(
    retained_rows,
    provider=page["run"]["provider"],
    root_thread=page["run"]["native_session"],
    model=page["run"]["model"],
)
```

retained_rows above means the accumulated owner-admitted invocation rows, not
just the first page. Existing detail routes own their bounded assembly and
truncation/unverified-boundary degradation. No read_detail wrapper is needed.
The authenticated owner is supplied by the HTTP adapter, never a client-selected
owner field. No Agent construction, Docker admission or login is required to
inspect retained activity.

Read-time translation remains the simplest existing approach. Capture-time
normalization is possible if original evidence is retained, but would be a
separate format migration. Cross-event aggregation still needs baselines,
correlation and later evidence: native cumulative usage, OpenCode snapshots,
export completion and model pricing cannot all be computed from one receipt.
Claude cost remains unknown; Codex API-equivalent estimates are not subscription
charges; OpenCode uses its own reported pricing evidence.

## Limits and pending work

Keep current capture completeness rules, owner isolation, truncation behavior,
unknown usage, source-cursor deduplication and wire projections. Neither a native
terminal event nor an empty page proves full capture or resource cleanup.

The reviewer verified store/routes/composition, projector wrappers and return
models, and searched relevant pricing/caller paths. Full timeline/telemetry
logic, relevant tests and live per-provider activity acceptance remain incomplete.
The legacy inference in ActivityStore.append and unqualified fallback are
existing internal concerns, not newly approved cleanup. Both retained copies
stay; no retention-policy change or migration is selected.

No implementation or specification change is authorized by the consultation
alone. Earlier PR approvals remain bounded to their reviewed work; this is a
design recommendation, not whole-PR merge approval.
