# Local Agent HTTP composition

`RunnerServer` binds the authenticated loopback-only local API to one concrete
Agent instance. Trusted host wiring may import the abstract base; public Agent
data contracts may not import this server or its implementation dependencies.

The module-level `RunnerRequestHandler` lives in `handler.py`. Its owner is an
explicit server instance reference, preserving the
existing routes, body limits, token comparison, response shapes and thread behavior.

The optional asynchronous resume operation is POST
`/v1/runs/{run}/resume/async`, returning an attempt observation with HTTP 202.
GET `/v1/runs/{run}/resume/{attempt}` reads the same durable observation.
These endpoints delegate to the base Agent's idempotent `ResumeDispatcher`;
synchronous resume shares their atomic per-run admission. These checks do not prove native integration
acceptance. `finished` describes completion of the resume call: inspect its
`result.status` for the provider outcome. `unknown` must not be replayed.
`do_GET` / `do_POST` are framework-mandated names; domain methods retain start,
resume, status, cancel and request-lookup meanings. Extraction is not a protocol change.

Readiness, execution outcome and cleanup are distinct. Async acknowledgement is
not completion; uncertain transport must be reconciled by existing identity.

Failed responses retain their status and response field names, but
`error_category` is always a safe domain machine code or the fixed
`runner_unclassified_failure` fallback. Generic exception messages are not codes,
even if their text resembles one. The optional `runner_diagnostics` envelope
contains HTTP status, a safe category,
fixed stage/failure kind and numeric OS errno when available. A fresh diagnostic
UUID correlates the response with its structured host log, even before a run
exists. Expected GET lookup 404s log at debug; other failures log warnings.
Paths, request bodies, credentials, raw exception text and tracebacks are excluded
from the response and diagnostics. Log records say failure, not refusal, because an execution
failure need not imply that nothing ran.

Wrappers pass the exception as private context to `_reply()`. A safe original
domain `code` and numeric errno survive even when the public error category is
mapped to a more general service error. Domain errors are classified before
their generic `ValueError` base; raw exception messages remain excluded.
