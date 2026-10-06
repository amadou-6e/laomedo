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
A bad lease now gets a terminal refusal without starving other leases in the
same tick. Accepted leases get best-effort exact revocation and cleanup if
processing fails. Live grant secrets are created exclusively with mode `0600`;
Windows ACL inheritance still needs a deployment check. The binding table
enforces one grant per lease token.
The authority now has a private SQLite approval record: a trusted controller
approves repository, branch, first-slice operations and invocation; the runner
consumes the opaque reference once for its saved run; the independent service
matches the lease claim to that durable record and pins the first lease token.
Without a matching record, writable launch fails closed. The local runner
passes only canonical scope values from this record; it cannot accept a
caller-supplied `github_scope` object. The controller API is in-process only:
its caller must establish actual user approval, and the local OS/service
identity separation is still unproven.

The bearer-capability `/v1/mediate` endpoint now belongs to an independent
`MediationHTTPService` class, not the lease service. It is intended to run in
a separate credential-owning process. Unit tests use separate server
objects/threads; the [synthetic process probe](RESULTS.md) additionally
shows the mediator surviving a hard kill of one lease-service process while
another lease service stays live. It does not prove production deployment. Its
credential-free HTTP tests show a revoked run is denied before transport,
another run remains usable, and both runs' grants expire at the authorizer
when the lease service stops renewing them. A narrow
credential-owning REST adapter covers PR create/update, reviewed issue
creation, Actions job read and same-repository REST read. It requires an
explicit token supplier and never falls back to ambient `gh`. It rejects
arbitrary API mutations, GraphQL and `git_push` visibly; this is **not** full
`git`/`gh` parity. PR updates need a target number and base from the trusted
grant record, plus a provider-side head/base preflight. The adapter has only
no-network tests. Its token supplier
has not been connected to a scoped GitHub identity, and the service's CLI
still starts only the old synthetic `GrantBook`.

These tests do not check a real Docker container, GitHub token, `git` push,
whole-tree kill, service manager, or model. The synthetic probe checks an
exact lease-service PID hard kill, not a runner or process-tree kill. There is no production mediator
deployment path or agent-container route to the loopback endpoint. Consequently
this remains an integration draft, not a reason to lift #97's draft status or to
accept Q11. The run-scoped grant remains short-lived (at most 60 seconds),
but a service failure can leave it usable until expiry; the live hard-kill
case in `AMENDMENT-01.md` and credential-source tests remain required.

Review dependencies: specs #150 and #250; Laomedo #97 and #103. A later
frozen experiment must exercise the deployed mediated path with a disposable
scoped GitHub identity before claiming actual write revocation.
