# Shared Agent activity

`ActivityStore` retains owner-scoped invocations, receipts and observations;
`ActivityCapture` observes one runner attempt. `CaptureIdentity` and `ActivityInvocation` in `models.py`
carry correlated values. `routes.py` presents the authenticated read-only API.

Vocabulary: `start` reserves capture identity; `bind` binds the actual remote run;
`append`-family operations retain observations; `finish` seals an observed outcome;
read methods inspect retained evidence without running a model. Exact method names
are listed below; record schemas and provider IDs do not change during renaming.

`projection.py` resolves the stored provider through `AgentProviderRegistry` and
adapts its canonical `ActivityProjection` to the existing response. Provider
`activity/projector.py` implementations own native interpretation and pricing.
`timeline.py` assembles normalized thread/turn/item observations using explicit
provider callbacks; it imports no provider implementation or pricing catalogue.
The pinned OpenAI API-equivalent catalogue belongs to Codex. Claude and OpenCode
without native rates retain unknown costs rather than borrowing Codex rates.
Partial capture cannot be upgraded merely because execution ended successfully.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `ActivityCapture` | `capture.py` | `__init__`, `feed`, `bind`, `observe`, `dispatched` |
| `CaptureIdentity` | `models.py` | `from_values` |
| `ActivityInvocation` | `models.py` | Validated fields / inherited interface |
| `Settings` | `settings.py` | `settings_customise_sources` |
| `ActivityStore` | `store.py` | `__init__`, `db`, `start`, `append`, `bind`, `graph_runs`, `claim_attempt`, `finish`, `runs`, `read` |

## Shared attempt and usage values

`ActivityAttemptRecord` in `models.py` constructs the common provider attempt
boundary. `to_record()` preserves optional `fresh_thread` omission and explicit
null end markers; `to_claude_record()` additionally retains Claude's original
field order. Provider services retain later lifecycle updates and historical
readers; a new record does not imply capture completeness.

`TokenUsage` groups the six normalized counters with their existing wire aliases;
`to_payload()` is the activity JSON boundary. OpenCode's own
`OpenCodeTokenUsage.to_activity_usage()` owns its native non-cached/non-reasoning
counter conversion. Unknown/incomplete native usage remains unknown and never
passes through a zero-filling constructor. Raw native item maps remain extensible
JSON, distinct from these closed, validated counters.

## Projection envelope

`ActivityProjection` in `models.py` owns the application response envelope,
not native interpretation. The name joins the domain `Activity` with the
responsibility `Projection`; there is one shared value, without a provider
subclass or an abstract base. Shared and OpenCode projector functions compose
it after their existing parsing, grouping, usage and pricing work. The dependency
direction is projector to shared model; the model does not import projectors.

| Method | Boundary and behavior |
| --- | --- |
| `to_payload()` | Return the existing shared field order, including diagnostics only when supplied. |
| `to_usage_first_payload()` | Return OpenCode's existing usage-before-telemetry field order. |

These projections return the original values and container references; they do
not recursively dump, copy or normalize native observations. Raw turns, items,
threads, diagnostics, telemetry, usage snapshots/points and cost evidence are
explicitly observed external structures: their typed fields skip new validation
and are excluded from the model representation. Partial counters, unknown fields
and explicit nulls stay intact, independently of `TokenUsage`. Application-owned
scalar metadata remains strict. An omitted diagnostics field stays omitted;
explicit empty diagnostics remain present. A frozen envelope does not freeze its
nested observations. Neither method mutates state or performs I/O.

Literal projector input/output cases live in
`tests/test_agents/test_activity/data/projector-records.json`; the envelope tests
check their exact projections and serialization. These are internal compatibility
controls, not a working graph demonstration or live provider acceptance.

## Normalized provider read boundary

BaseAgent.read_activity returns ActivityPage and append-only ActivityRecord values.
Provider Agents pass their native projection function to internal ActivityNormalizer
(normalizer.py), which reads only retained, attempt-bounded evidence. SQLite
transaction ownership serializes normalized sequence allocation across processes;
unchanged replacement snapshots do not append another record. Messages/tool output
replace prior versions by thread/ID, usage is an absolute attempt snapshot (never
summed across revisions). Full shared ActivityProjection travels with a monotonic
projection_revision so telemetry/cost/thread-only changes survive ingestion.

ActivityNormalizer.read validates the run/attempt, clips both physical sources,
normalizes and journals atomically, then returns bounded records. It starts no
container/model/auth operation. The private journal is a normalization cache, not
an execution record. ActivityCapture consumes /activity, retains common records
and display snapshots with attempt-scoped deduplication and seals only drained
closed pages. Application projection reads common snapshots without provider
selection. Native parser helpers remain internal to providers.
