# Claude local authentication adapter

The provider-specific `mirror_login` function copies only the authorized access
credential into the dedicated local volume. Host refresh ownership stays on the
host. This is not a generic credential store or permission to copy profiles,
rotating refresh credentials, sessions or settings.

`Settings` reads explicitly supported local opt-in configuration at point of use.
`LocalClaudeLoginError` preserves stable public outcome codes. No README, repr,
dump, graph or validation evidence may contain credential values.

## Proposed mirror repair — not implemented

The existing CLI copy has no durable ownership receipt. A failed actual graph
stopped before a native turn; its original low-level cause is unknown. The repair
will consume py-docker's owned Session lifecycle instead of adding another Docker
worker or transport. The SDK deadline contract remains request admission and
socket inactivity control, not a hard wall-time guarantee.

The design has received read-only Claude review; its R3 corrections and catalog
proposal still require review. This README is a design checkpoint, not evidence
of successful copying, authentication or graph execution.

| Concern | Owner / name | Interface and effects |
| --- | --- | --- |
| Exact access-only payload | `models.py`: `ClaudeAccessLoginRecord` | `from_host_record` constructs the selected value; `to_private_bytes` retains original JSON bytes. Secret fields are excluded from ordinary dumps and reprs. |
| Host configuration | `settings.py`: `Settings` | Read the existing opt-in and proposed private-state override at point of use; explicit invocation snapshots must not fall through to ambient settings. |
| Copy coordination | `utils.py`: `mirror_login` | Preserve its existing arguments; select/admit the local endpoint, verify volume labels, validate source and fixed required expiry, write through owned stdin, then confirm exit and exact cleanup. |
| Private directory permissions | `host/private_state/` | Generic lexical path and permissions mechanisms; Claude owns its leaf path, receipt name and public error mapping. |

Names follow responsibility: `Record` is a value with an explicit private
projection; `Settings` owns host configuration. No new abstract base, auth cache,
diagnostic Store or independent receipt model is planned. Classes and standalone
functions remain in separate implementation files.

The proposed copy preserves selected-key order, omitted versus explicit null,
integer versus float expiry, Unicode escaping and default JSON spacing. It never
duplicates a rotating refresh credential. Host refresh ownership stays unchanged.
Cleanup uncertainty takes precedence and retains the exact pending receipt.

The proposed removal of the duplicate Resume admission copy changes error
precedence and is under named review. Catalog preparation and cache freshness are
also a separate named proposal; they are not implemented by this checkpoint.

### Payload model checkpoint

`ClaudeAccessLoginRecord` is now implemented and has internal compatibility
controls against 96 frozen old-writer outputs. The existing mirror coordinator
still uses its original code; no new Docker copy, authentication or native turn
has run. The record keeps each named optional field as already parsed JSON with
`SkipValidation[JsonValue]`, preserving the old writer's opaque native values and
recursion behavior. This exception is an explicit external-format boundary,
not an untyped application payload. Every field is excluded from ordinary dumps.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `LocalClaudeLoginError` | `errors.py` | `__init__` |
| `Settings` | `settings.py` | `settings_customise_sources` |
