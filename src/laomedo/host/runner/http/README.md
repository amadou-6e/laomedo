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
they do not change synchronous resume admission or prove native integration
acceptance. `finished` describes completion of the resume call: inspect its
`result.status` for the provider outcome. `unknown` must not be replayed.
`do_GET` / `do_POST` are framework-mandated names; domain methods retain start,
resume, status, cancel and request-lookup meanings. Extraction is not a protocol change.

Readiness, execution outcome and cleanup are distinct. Async acknowledgement is
not completion; uncertain transport must be reconciled by existing identity.
