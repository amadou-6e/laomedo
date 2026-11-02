# Claude local authentication adapter

The provider-specific `mirror_login` function copies only the authorized access
credential into the dedicated local volume. Host refresh ownership stays on the
host. This is not a generic credential store or permission to copy profiles,
rotating refresh credentials, sessions or settings.

`Settings` reads explicitly supported local opt-in configuration at point of use.
`LocalClaudeLoginError` preserves stable public outcome codes. No README, repr,
dump, graph or validation evidence may contain credential values.

## Mirror repair — implemented draft, live validation pending

The existing CLI copy has no durable ownership receipt. A failed actual graph
stopped before a native turn; its original low-level cause is unknown. The repair
now consumes py-docker's owned Session lifecycle instead of adding another Docker
worker or transport. The SDK deadline contract remains request admission and
socket inactivity control, not a hard wall-time guarantee.

The design has received read-only Claude review. The final repair preserves the
existing Resume admission copy: removing it could consume a completed run's
resumability before authentication succeeds. Catalog/caching redesign is excluded
from this increment; explicit Refresh continues to request fresh discovery, and
its existing authentication path also uses the changed mirror policy below.
This README describes a draft implementation, not evidence
of successful copying, authentication or graph execution.

| Concern | Owner / name | Interface and effects |
| --- | --- | --- |
| Exact access-only payload | `models.py`: `ClaudeAccessLoginRecord` | `from_host_record` constructs the selected value; `to_private_bytes` retains original JSON bytes. Secret fields are excluded from ordinary dumps and reprs. |
| Host configuration | `settings.py`: `Settings` | Read the existing opt-in and private-state override at point of use; explicit invocation snapshots do not fall through to ambient settings. |
| Copy coordination | `utils.py`: `mirror_login` | Preserve its existing arguments; select/admit the local endpoint, verify volume labels, validate source and fixed required expiry, write through owned stdin, then confirm exit and exact cleanup. |
| Private directory permissions | `host/private_state/` | Generic lexical path and permissions mechanisms; Claude owns its leaf path, receipt name and public error mapping. |
| Container-side write protocol | `resources/write_login.py`: `write_login` | Read the declared bytes without waiting for pipe EOF; preserve refresh-capable logins; replace the access-only file atomically. |

Names follow responsibility: `Record` is a value with an explicit private
projection; `Settings` owns host configuration. No new abstract base, auth cache,
diagnostic Store or independent receipt model is planned. Classes and standalone
functions remain in separate implementation files.

The copy preserves selected-key order, omitted versus explicit null,
integer versus float expiry, Unicode escaping and default JSON spacing. It never
duplicates a rotating refresh credential. Host refresh ownership stays unchanged.
Cleanup uncertainty takes precedence and retains the exact pending receipt.

The duplicate Resume admission copy is deliberately retained. Catalog preparation
and cache freshness remain separate work. Cold catalog discovery has no newly
claimed 30-second completion guarantee.

### Payload model checkpoint

`ClaudeAccessLoginRecord` is now implemented and has internal compatibility
controls against 96 frozen old-writer outputs. The existing mirror coordinator
now uses that model; no new Docker copy, authentication or native turn has run.
The record keeps each named optional field as already parsed JSON with
`SkipValidation[JsonValue]`, preserving the old writer's opaque native values and
recursion behavior. This exception is an explicit external-format boundary,
not an untyped application payload. Every field is excluded from ordinary dumps.

### Operation policy and remaining constraints

Copy admission uses one 90-second normal deadline, clipped to an existing attempt
deadline when present, plus a distinct 20-second SDK cleanup reserve. Initial
context selection and SDK construction retain clipped per-request timeouts.
Windows named-pipe connect retries and socket inactivity behavior do not provide
a finite hard wall-time guarantee. These policies are normal operation limits,
not experiment allowances. No automatic copy or model retry is introduced.

Private receipts live under the current user's local state directory, outside
Git. `LAOMEDO_CLAUDE_LOGIN_STATE_DIR` is a trusted host-only absolute override.
Existing leaves must already have verified private permissions; their ACLs are
not rewritten. The receipt name is stable per dedicated profile, allowing the
SDK to reconcile prior intent under its existing receipt lock before dispatch.
The optional runner dependency pins reviewed, unpublished py-docker commit
`49652f4`; its explicit log-driver extension passed focused code/spec review. The mirror
requires `log_driver="none"`; real copying is blocked until this request and its
readback are validated against the real engine. This is not a claim that the SDK
is merged or published.

During an actual attempt, the native authentication stage recalculates remaining
time after copying and receives the same absolute attempt deadline. Resume's
pre-admission copy and explicit catalog Refresh semantics are unchanged. The
earlier failed graph remains historical failure evidence until a new real run
validates this exact source revision.

Resume's admission copy can occupy the HTTP request through the normal
90-second copy policy and separate 20-second cleanup reserve. This is longer
than the former individual 20-second CLI call limits and is not a hard wall-time
guarantee. No automatic retry is added.

### Discovery, preflight and startup timing

When `LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN=1`, the same mirror runs wherever
`ClaudeAgent._check_auth()` is called, including model discovery and preflight.
The 90-second copy policy and separate 20-second cleanup reserve therefore also
apply to these paths. They are stage policies, not a promise that the whole
request finishes within their sum; the SDK/named-pipe limitations above still
apply. These timings do not apply a new model-turn allowance.

| Entry point | Actual work and caller limit |
| --- | --- |
| Model **Refresh**, initial/upgrade discovery and model/runner field refresh | The Langflow component calls `GET /v1/models`, which invokes `editor_model_catalog()` with `refresh=True`. The discovery owner mirrors without an enclosing discovery deadline, then checks native authentication with `timeout=15`, then sends the initialize-only control with `timeout=45`. Container startup, result collection and cleanup are additional stages; 45 seconds is not an end-to-end request limit. |
| A concurrent catalogue request | It shares the existing owner's `Future` but waits only 65 seconds. Expiry returns `runner_model_catalog_unavailable_check_runner_connection`; it does not cancel the owner or prove its copy/cleanup stopped. |
| CLI startup `warm_catalog` | A daemon thread calls `model_catalog()` while the HTTP server starts. It follows the same discovery/mirror path, catches `RunnerError`, and can populate the cache later. `/v1/health` reporting ready does not establish catalogue or account readiness. A subsequent editor Refresh still requests fresh discovery rather than simply reading that cache. |
| Python `preflight()` | It mirrors, then checks native authentication with the default `timeout=20`. It has no enclosing preflight deadline here and does not call model initialization. This is a Python method, not a separate preflight button or HTTP endpoint. |

The Claude graph component sets `catalog_timeout_seconds=75`; the shared
component's 30-second default is overridden for Claude. Both this 75-second HTTP
wait and a concurrent request's 65-second wait can expire before the discovery
owner finishes. A disconnected or timed-out caller does not cancel discovery;
the owner may still finish and cache its result. The source docstring's claim
that discovery stays below the component HTTP deadline is not an implemented
aggregate guarantee.

The UI can report a model-list failure while its local runner remains healthy.
The existing Refresh/loading affordances do not show copy-stage progress,
remaining time or whether a timed-out discovery has ended. There is no
model-discovery cancellation or completion-status control. Avoid repeatedly
pressing Refresh or restarting a healthy runner in response to this timing
mismatch; neither confirms the earlier copy/cleanup outcome. Check the configured
runner account login if discovery continues to fail. A failed login copy must
retain any pending receipt; do not remove that receipt or repeat a copy before
its ownership and cleanup have been reconciled. Status and Activity for existing
runs remain separate from model discovery. Refresh, startup warming and preflight
do not submit a model turn or rerun a graph.

An aggregate discovery deadline, observable completion/cancellation and matching
UI recovery require a separate code/UI follow-up. This documentation does not
extend timeouts, claim that the mismatch is repaired, or establish real-browser
acceptance.

Local endpoint admission deliberately requires the canonical lowercase
`npipe:////./pipe/<name>` spelling (or an absolute Unix socket). Alternate pipe
spellings accepted by some Docker CLI versions are refused before reading the
credential. Windows directory admission and its unverified elevated-session
constraint are documented in `host/private_state/README.md`.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `LocalClaudeLoginError` | `errors.py` | `__init__` |
| `Settings` | `settings.py` | `settings_customise_sources` |
| `ClaudeAccessLoginRecord` | `models.py` | `from_host_record`, `require_expiry_after`, `to_private_bytes` |
