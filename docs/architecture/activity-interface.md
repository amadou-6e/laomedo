# Activity interface: design sketch

Proposal for #277, based on implementation `0b923899`. No Activity implementation
changes are included. Claude's initial design review requested revisions to the
runner reader and left detail assembly unread. The revised detail ownership
below is unreviewed: the follow-up was quota-refused until 21:00 Europe/Berlin
on 2026-11-10. This document is not an implementation-ready approval.

## Objects and ownership

Use existing objects, with two new shared methods. Add no reader ABC, separate
session object or provider-specific storage implementation.

| Object | Material type | Implementation supplied by | Operation |
| --- | --- | --- | --- |
| BaseAgent | Existing Python ABC, with a new concrete method | Shared Laomedo code, inherited by all providers | Read one runner run/capture's retained feeds. |
| ActivityStore | Existing concrete Python class, with a new concrete method | Shared Laomedo code | Read owner-scoped invocation detail and assemble its bounded projection. |
| BaseActivityProjector | Existing Python ABC | ClaudeActivityProjector, CodexActivityProjector, OpenCodeActivityProjector | Translate captured receipts into the existing ActivityProjection. |
| ActivityCapture | Existing concrete observer | Shared capture code with existing provider rules | Follow both feed cursors and record capture completeness/outcome. |
| ActivityProjection | Existing Pydantic model | Shared value returned by projectors | Timeline, threads/items, telemetry, usage and cost observations. |

The provider implementer supplies only the existing projector for this boundary.
Laomedo owns storage access and capture observation. Native history acquisition
remains inside provider execution: reads must not start a container, refresh
login, invoke a native CLI or import arbitrary home-directory session history.

## Exact Python declarations

These are excerpts from their respective existing objects, not replacement
classes. New methods are marked; all methods are synchronous.

```python
class BaseAgent(ABC):
    # New shared concrete method; providers do not override it.
    def read_activity(
        self,
        run_id: str,
        attempt_id: str | None = None,
        *,
        native_after: int = 0,
        otel_after: int = 0,
        limit: int = 100,
        tail: bool = False,
    ) -> dict:
        """Read the existing attempt-bounded runner /events payload."""


class ActivityStore:
    # Existing shared read methods.
    def runs(self, owner: str, flow: str, node: str) -> list[dict]: ...

    def graph_runs(
        self, owner: str, flow: str, execution: str | None = None,
    ) -> list[dict]: ...

    def read(
        self, owner: str, flow: str, node: str, run: str,
        after: int = 0, limit: int = 100,
    ) -> dict: ...

    # New shared read-model assembly method.
    def read_detail(
        self, owner: str, flow: str, node: str, run: str,
    ) -> dict:
        """Return bounded invocation receipts and their existing projection."""


class BaseActivityProjector(ABC):
    # Existing explicit wire-order policy, not a provider detector.
    usage_first_payload: bool = False

    @classmethod
    @abstractmethod
    def accepts(cls, events: list[dict]) -> bool:
        """Recognize legacy unqualified receipts for internal callers only."""

    @abstractmethod
    def project(
        self,
        events: list[dict],
        *,
        root_thread: str | None = None,
        model: str | None = None,
    ) -> ActivityProjection:
        """Translate retained receipts without execution or invented totals."""
```

Keep existing complete read payloads as dictionaries and reuse the existing
ActivityProjection. Do not introduce a partial ActivityPage model or validate
arbitrary native receipt fields into a new schema. BaseActivityProjector should
be exported through agents/agents/base/__init__.py, as the other public provider
contracts are. Implementation imports continue to use defining modules.

BaseAgent.read_activity uses its own status/_run_dir admission internally. The
HTTP handler stops reaching into provider-private paths. This is why a separate
RunnerActivityReader(state_directory) is unnecessary.

ActivityStore.read_detail extracts the existing route's bounded load/assembly
logic and delegates translation through existing projection.py/registered
projectors; it contains no provider-native parser or pricing rules. This keeps
one owner-qualified read interface and avoids a one-method ActivityReader
wrapper. This ownership choice still needs Claude's missing detail-scope review.
Current activity/models.py imports ActivityStore; any projection import used by
read_detail must preserve module initialization order, not introduce an eager
store -> projection -> base/models -> activity/models import cycle.

## Caller experience

Runner-side observation uses the same Agent object as interaction:

```python
page = agent.read_activity(
    run_id,
    activity_attempt_id,
    native_after=0,
    otel_after=0,
    limit=100,
)
if page["accepted"]:
    next_page = agent.read_activity(
        run_id,
        activity_attempt_id,
        native_after=page["next_after"],
        otel_after=page["telemetry"]["next_after"],
    )
```

A page with accepted=False has no cursor or telemetry fields; retry the same
bound identity/cursors later if appropriate. Never substitute the latest attempt.

Application-side history uses its authenticated owner's existing store:

```python
store = ActivityStore(database_path, read_only=True)
detail = store.read_detail(
    owner=str(authenticated_user.id),
    flow=flow_id,
    node=node_id,
    run=invocation_id,
)
timeline = detail["projection"]
```

The run argument above is the Activity database invocation ID, not the runner
run ID. Retaining that parameter preserves the existing Store vocabulary; the
caller explicitly names its source. The URL/body never supplies owner identity.
Read-only construction does not create a missing database.

The provider-facing call remains:

```python
projector = ClaudeActivityProjector()
projection = projector.project(
    retained_invocation_receipts,
    root_thread=native_thread_id,
    model=reported_model,
)
payload = projection.to_payload()
```

retained_invocation_receipts means the owner-admitted accumulated store rows,
not a raw runner page. OpenCode retains its existing explicit usage-first wire
projection. Application composition uses stored provider identity through the
existing AgentProviderRegistry, not a provider name supplied by the reader.

## Identities and cursor behavior

| Value | Scope |
| --- | --- |
| run_id on BaseAgent | Durable runner run, which can be resumed. |
| attempt_id | Exact native/OTLP capture boundary; never guessed from the native thread. |
| run on ActivityStore | One owner/flow/node invocation ID in SQLite. |
| native thread_id | Provider conversation; neither authorization nor capture completion. |
| native_after, otel_after | Independent physical JSONL line offsets. |
| after on ActivityStore.read | Local retained receipt sequence, not either file offset. |

Runner reads retain start/end bounds, separate cursors, existing byte/page limits
and the complete-newline rule. A partial trailing write is retried, not consumed.
Tail reads retain the existing whole-file-to-boundary usage baseline, including
records before this attempt's start. That baseline is not new token usage.
An exactly full page can report has_more=True even if no next record exists.

Empty data or has_more=False does not establish capture completion. A follower
must consume both explicit closed bounds. Native turn/completed is not evidence
of host-run finalization, cleanup or capture completeness.

The current future-cursor limitation is unchanged: a caller supplying an offset
past the current file can skip later receipts below that offset. The production
follower uses only server-returned cursors. Rejecting future offsets requires a
separately selected behavior change; this extraction will not add a test whose
sole purpose is to enshrine the bug. Test valid append/follow/resume behavior.

## Validation and missing-attempt policy

- Missing/empty attempt and an unknown/not-yet-published attempt retain the
  existing accepted=False envelope for valid query input. No latest-attempt fallback.
- The shared method admits run and attempt IDs through current rules before file
  access and reads the latest status through its owning Agent.
- HTTP parsing remains explicit: do not put a multi-line Pydantic or raw Python
  exception into error_category. Non-numeric cursor/limit becomes the existing
  invalid_activity_cursor category with the current runner error status404.
- A missing attempt can still bypass cursor parsing as today. For a supplied but
  unknown attempt plus malformed numeric input, parsing before file lookup can
  intentionally change the previous200 into404. This small validation tightening
  must be selected explicitly during implementation; do not promise exact wire
  equivalence for malformed inputs while changing parse order.
- Parsed negative cursor integers are currently clamped to the attempt's start;
  they are not universally rejected by the existing HTTP path. Keep that behavior
  unless stricter validation is selected. Valid limit remains1..200 once read.
- A closed boundary must have both integer ends, each no earlier than its start.
  Partially published/malformed closure must fail with the existing
  activity_attempt_identity_mismatch category, rather than uncaught KeyError or
  invented closure. This is an explicit defensive tightening for malformed data.

The final parsing order and malformed-input outcomes are design decisions, not
implemented changes. Valid existing URLs and payload fields remain unchanged.

## Capture completeness and projection ownership

ActivityCapture.observe keeps the completion decision, finish reason and
provider-specific rules unchanged. OpenCode currently uses capture_complete /
native_stream_complete and a component-name check; other paths track observed
native terminal receipts. This proposal does not silently replace that seam.
Stopping observation does not cancel execution or close a native session.

ActivityStore.read_detail pages by200 up to the existing20000-receipt cap. It
uses stored provider, native_session and model, and retains the existing detail
response keys and field presence. If truncated or invocation boundary is
unverified, retain today's degradation: unknown aggregate usage/cost, no complete
per-turn totals, cleared usage points and explicit explanatory cost_reason.
Do not interpret one arbitrary page as a complete projection or cache partial
totals as final. An incremental projection checkpoint is outside this work.

Provider differences remain inside existing projectors and capture:

| Provider | Interpretation to preserve |
| --- | --- |
| Codex | Thread/turn/item/usage receipts and explicit parentage; pinned API-equivalent pricing is distinct from billed cost. |
| Claude | Native receipts/telemetry, diagnostics, explicit thread correlation; missing usage/pricing stays unknown, never borrowed Codex rates. |
| OpenCode | Retained message/history and step/baseline usage conversion; native post-shutdown history read stays execution-owned; existing snapshot/partial-capture and usage-first payload rules remain. |

No reader opens raw login files, account/RPC responses or arbitrary native
session paths. Existing capture filtering/redaction remains required; projection
is not a replacement for it. Frozen ActivityProjection does not make nested
native observations immutable.

## HTTP interfaces and files

| Existing HTTP interface | Target owner |
| --- | --- |
| Runner GET /v1/runs/{run}/events | BaseAgent.read_activity |
| App GET /api/v1/laomedo/agent-activity/{flow}/{node} | ActivityStore.runs |
| App GET /api/v1/laomedo/agent-activity/{flow}/{node}/{invocation} | ActivityStore.read |
| App GET /api/v1/laomedo/agent-executions/{flow} | ActivityStore.graph_runs |
| App GET /api/v1/laomedo/agent-executions/{flow}/{node}/{invocation} | ActivityStore.read_detail |

Authentication, no-store/nosniff, owner/flow/node isolation, missing-store503
and missing/foreign-owner404 stay with current HTTP adapters. Missing/foreign
owner reads remain indistinguishable. Existing FastAPI threadpool use remains;
no new SSE/WebSocket or asynchronous native iterator is implied.

```text
agents/agents/base/agent.py          # shared concrete read_activity
agents/agents/base/base.py          # existing BaseActivityProjector
agents/agents/base/__init__.py      # export existing projector ABC
agents/activity/store.py           # existing reads + proposed read_detail
agents/activity/models.py          # existing ActivityProjection/capture values
agents/activity/projection.py      # existing provider composition/wire projection
agents/activity/routes.py          # auth/routes; delegate detail read
agents/activity/capture.py         # existing completeness owner
agents/activity/runner/feed.py     # existing physical feed logic
agents/agents/<provider>/activity/  # existing native projectors/helpers
```

## Acceptance before claiming completion

1. Shared method declarations are discoverable; host code uses no undeclared
   provider-specific activity members. No new per-provider storage implementations.
2. No/unknown/open/closed/resumed capture reads preserve valid payloads; native
   and OTLP cursors stay independent, incomplete writes are retried, tail baselines
   are not charged again, and a closed attempt cannot include a later attempt.
3. Explicit tests cover selected malformed-input/closure categories and parsing
   order, without locking unrelated known bugs in as required behavior.
4. Owner/flow/node isolation, read-only missing DB behavior, error statuses and
   HTTP headers remain intact; stored provider takes precedence over event markers.
5. Receipt retry/deduplication, unknown/partial counters, uncorrelated threads,
   pricing uncertainty, truncation and unverified-boundary degradation retain all
   existing response keys and omission/null semantics. Fixtures are internal
   controls, not real native acceptance.
6. Capture completion stays with ActivityCapture and remains independent of run
   success, native terminal messages and resource cleanup.
7. Real Codex fresh/resume/cancel capture must be read through the activity
   boundary and projected, not inferred from an execution-only log. Claude and
   OpenCode capture acceptance needs real evidence or an exact blocker.
8. Review must finish the previously unread detail/store/projector scope and
   settle the two malformed-input tightening decisions before implementation.

Reviewer status: initial proposal REVISE; revised runner ownership follows its
recommendation, but this revised sketch is not approved. Detail ownership and
projection coverage remain reviewer pending. No implementation is included.
