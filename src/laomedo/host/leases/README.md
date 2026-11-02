# Lease and grant values

`ContainerIdentity` groups the existing private container registration.
`LeaseGrant` groups the in-memory grant identity, excluded secret lease binding,
wall/monotonic deadlines and revocation observation. `renew()` updates the related
deadlines together, `revoke()` records revocation and `accepts()` checks both
clock domains. `GrantBook` retains locking, random grant issuance and audit writes.

`LeaseRevocationRecord` and `LeaseRefusalRecord` construct new cleanup/audit
records using `to_record()` at the existing JSON writer. Optional fields are
omitted unless observed. Historical lease readers and independent container
cleanup remain unchanged. No model confers authority or confirms unobserved cleanup.

`LeaseCleanupObservation.from_result()` admits an injected cleanup callback's
verdict and diagnostic together. Invalid verdicts or non-JSON diagnostics are
recorded as the existing `cleanup_error` with cleanup unverified, so a malformed
callback cannot lose the result journal or imply successful cleanup.

## HTTP server and request handler

`server.py` owns `LeaseHTTPServer`, the concrete loopback HTTP listener. Its
constructor retains the supplied `book`, `mediator`, `transport` and `instance`
on the server before the framework binds the listener. `handler.py` owns the
module-level `LeaseRequestHandler`, the framework adapter for those services.
The handler reads its owning server's references; it does not capture them in
a constructor-local class or import the server at runtime.

The naming vocabulary is `HTTPServer` for listener ownership and
`RequestHandler` for one framework request. `LeaseHTTPServer.__init__` wires the
existing dependencies and handler; inherited `serve_forever`, `shutdown` and
`server_close` retain their framework names. `LeaseRequestHandler.do_GET` handles
the existing health route, `do_POST` handles mediation then lease writes in the
existing order, `_json_reply` emits the existing JSON bytes/headers, and
`log_message` suppresses default access logging. No new endpoint, policy, reply
model or authentication behavior is introduced by the extraction.

Dependency direction is server to handler, with type-only references in the
reverse direction. The handler calls the existing grant/mediation services and
uses their existing public error category. Tiny exact wire replies remain at
the HTTP boundary; this refactor does not create duplicate domain models.

The structural regression check covers maintained production Python under
`src/`, `components/` and `tools/`, including this handler. Historical experiments,
retained probes and inherited test/example doubles are excluded from that guard;
their unchanged nested declarations are not claimed to comply with this policy.

## First loss and I/O diagnostics

`LeaseLossObservation` owns a validated reason and optional age. Existing health
comparisons and 5s/3s/TTL constants remain unchanged. The client sets lost/cancel
events before any model/log/I/O work; it then retains the first observation in
`loss` and best-effort writes `loss.json`. A failed observation stays unavailable,
not relabelled as a later trigger. `finish()` keeps the received external result
privately in `result` before its existing rejection predicate; consumers project
cleanup through the existing model instead of serializing that raw receipt.

OS failures remain log-only: fixed wall/monotonic stage, known OS class and numeric
errno/WinError. No raw message, filename, token, instance or path is logged. New
diagnostic failures never suppress security events or change existing I/O retries.
