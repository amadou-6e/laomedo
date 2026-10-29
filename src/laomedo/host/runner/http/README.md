# Local Agent HTTP composition

`RunnerServer` binds the authenticated loopback-only local API to one concrete
Agent instance. Trusted host wiring may import the abstract base; public Agent
data contracts may not import this server or its implementation dependencies.

The nested request handler will be extracted to `handler.py` as a module-level
object. Its owner will be an explicit server instance reference, preserving the
existing routes, body limits, token comparison, response shapes and thread behavior.
`do_GET` / `do_POST` are framework-mandated names; domain methods retain start,
resume, status, cancel and request-lookup meanings. Extraction is not a protocol change.

Readiness, execution outcome and cleanup are distinct. Async acknowledgement is
not completion; uncertain transport must be reconciled by existing identity.
