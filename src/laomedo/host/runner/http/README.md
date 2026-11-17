# Local Agent HTTP composition

`RunnerServer` binds the authenticated loopback-only local API to one concrete
Agent instance. Trusted host wiring may import the abstract base; public Agent
data contracts may not import this server or its implementation dependencies.

The module-level `RunnerRequestHandler` lives in `handler.py`. Its owner is an
explicit server instance reference, preserving the
existing routes, body limits, token comparison, response shapes and thread behavior.
`do_GET` / `do_POST` are framework-mandated names; domain methods retain start,
resume, status, cancel and request-lookup meanings. Extraction is not a protocol change.

Readiness, execution outcome and cleanup are distinct. Async acknowledgement is
not completion; uncertain transport must be reconciled by existing identity.

Failed responses add an optional `runner_diagnostics` envelope, without changing
status or existing response fields. It contains HTTP status, a safe category,
fixed stage/failure kind and numeric OS errno when available. A fresh diagnostic
UUID correlates the response with its structured host log, even before a run
exists. Expected GET lookup 404s log at debug; other failures log warnings.
Paths, request bodies, credentials, raw exception text and tracebacks are excluded
from diagnostics. Existing raw wire exception fields are not newly copied into
graph diagnostics. Log records say failure, not refusal, because an execution
failure need not imply that nothing ran.
