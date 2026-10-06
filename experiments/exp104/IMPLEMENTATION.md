# #104 mediated lease bridge (draft implementation)

This branch combines the unmerged #97 lease service and #100 mediation core
without changing either source branch. It does **not** constitute a real
GitHub credential or model-stage experiment.

The independent `LeaseService` can be given a trusted `MediationStore`. In
that mode, an accepted lease atomically persists the grant and its exact
run/lease/service binding before writing the acknowledgement. A missing or
malformed mediation request gets no acknowledgement. A supplied trusted
authority must match the runner-side request against the saved run; without
it, mediated lease creation refuses dispatch. If acknowledgement
writing fails, the grant is revoked. Heartbeat loss revokes the exact run's
grant before exact-container cleanup. A new service instance revokes all
grants for its state scope; it does not silently adopt old leases. Fresh
heartbeats renew only live grants, never expired or revoked ones. The runner
notices a changed service instance. A failed pre-launch path preserves its
original error while finishing any accepted lease.

The tests use a fake effect transport and mocked container cleanup. They
check another run remains usable, the grant is denied *inside* the cleanup
callback, restart denial, failed acknowledgement, and malformed requests.
They do not check a real Docker container, GitHub token, `git`/`gh` adapter,
whole-tree kill, service manager, or model. The `serve` CLI still starts the
old synthetic `GrantBook`; there is no production mediator deployment path.
The test authority is a fixed fixture, not a production run-record lookup.
No stage-facing mediated operation endpoint exists yet. Consequently this is
an internal bridge for review, not a reason to lift #97's draft status or to
accept Q11. The run-scoped grant remains short-lived (at most 60 seconds),
but a service failure can leave it usable until expiry; independent service
failure and credential-source tests remain required.

Review dependencies: specs #150 and #250; Laomedo #97 and #103. A later
frozen experiment must exercise the deployed mediated path with a disposable
scoped GitHub identity before claiming actual write revocation.
