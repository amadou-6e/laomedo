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
resumability before authentication succeeds. Catalog preparation is excluded
from this increment; explicit Refresh continues to request fresh discovery.
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
