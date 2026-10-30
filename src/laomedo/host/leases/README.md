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
