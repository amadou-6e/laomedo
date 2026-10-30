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
