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
The runner now stages heartbeat and lease metadata outside the directory the
service scans, then publishes the complete registration with one directory
rename. This removes the gap in which a normal runner could be permanently
refused because the service saw its empty directory. A refused lease gets an
early, sanitized refusal record, so the runner can report the error while
exact cleanup continues; only the final result claims cleanup status. An
interrupted runner can leave an unscanned staging directory; it
cannot receive a grant from that directory. A transient database failure
still causes fail-closed terminal lease handling rather than automatic retry;
whether to tolerate short locks is an open reliability choice.
The authority now has a private SQLite approval record: a trusted controller
approves repository, branch, first-slice operations and invocation; the runner
consumes the opaque reference once for its saved run; the independent service
matches the lease claim to that durable record and pins the first lease token.
Without a matching record, writable launch fails closed. The local runner
passes only canonical scope values from this record; it cannot accept a
caller-supplied `github_scope` object. The controller API is in-process only:
its caller must establish actual user approval, and the local OS/service
identity separation is still unproven.

The trusted approval can now pin a non-secret GitHub `connection_id` and
credential generation alongside the run scope. A trusted connection
authorizer must confirm that generation, repository and operator before the
approval is saved; the mediator checks the same generation at grant issue and
again before every effect. A rotated or disconnected connection therefore
refuses a still-active run's *new* effect while another connection continues.
The bound grant passes its identity/generation to the credential-owning
transport, whose supplier must accept that context; a legacy zero-argument
supplier cannot silently service it. Existing unbound draft grants remain
supported for migration and synthetic tests, but they are not a production
account-connection path. The concrete connection registry and secret custody
are not implemented in this branch; synthetic #108 examines those separately.

The bearer-capability `/v1/mediate` endpoint now belongs to an independent
`MediationHTTPService` class, not the lease service. It is intended to run in
a separate credential-owning process. Unit tests use separate server
objects/threads; the [synthetic process probe](RESULTS.md) additionally
shows the mediator surviving a hard kill of one lease-service process while
another lease service stays live. It does not prove production deployment. Its
credential-free HTTP tests show a revoked run is denied before transport,
another run remains usable, and both runs' grants expire at the authorizer
when the lease service stops renewing them. A narrow credential-owning REST
adapter covers PR create/update, reviewed issue creation, Actions job read and
same-repository REST read. It requires an explicit token supplier and never
falls back to ambient `gh`. It rejects arbitrary API mutations and GraphQL;
this is **not** full `git`/`gh` parity. PR updates need a target number and
base from the trusted grant record, plus a provider-side head/base preflight.

The new host-only `GitHubGitTransport` handles one narrow `git_push`: an exact
local commit to an approved *new* branch in one configured repository. It
stages the real objects in a fresh bare repository without provider credentials,
checks the baseline ancestry and outgoing workflow-file diff **there**, then
pushes those same staged objects with replace refs disabled. A regression
uses a checkout-local Git replace ref to conceal a workflow edit and verifies
the edit is still refused. The absent-ref lease prevents overwriting an
existing branch; branch updates and full `git` parity are not implemented.
A rejected or lost Git response is uncertain, not retried. The
Git credential helper gets a selected token only in the host mediator's
short-lived subprocess environment. It receives no ambient `gh` login, Git
Credential Manager configuration, token-bearing URL or agent mount. The CLI
can now launch the mediator and lease service independently with explicit
private stores and selected connection identity. Synthetic integration tests
cover the push path, revocation of A without stopping B, connection
replacement and startup composition.

For bounded `EXP-104-D2`, `HostTokenConnection` reads the user-supplied `GH`
key from a host file excluded from the agent's source mount. Replacing or
removing that file refuses new effects. This is **test-only custody**, not
browser login or a production registry/secret vault. The user-authorized
token is broader than the original scoped-token protocol; amendments 05–06
record the deviation. A read-only preflight authenticated it as `ga84jog` but
could not access the original disposable repository. One attempt to create
the alternate private repository was explicitly rejected with HTTP 403; a
read-back still returned 404. The user then created the public alternate
repository, which was initialized once under amendment 08. The first D2
identity pushed a branch but stopped after a C admission race and remains
incomplete. Fresh identity `-02` completed the bounded runner-loss diagnostic;
the machine observation and exact provider journal are linked from
[RESULTS.md](RESULTS.md). The tested revision temporarily widened the
default first-slice approval set for B's read. The later correction restored
the narrow default and put that read behind an explicit diagnostic-only
opt-in; its live path has not been rerun.

Amendment 07 records another pre-run validity fix: the original instruction
to try a *different* branch with A's revoked capability cannot test
revocation when A is bound to exactly one branch. The diagnostic will use a
fresh effect on the same approved branch and require `grant_unavailable`
before provider transport; the original acceptance wording still needs a
reviewed correction. The mediator now records non-secret provider-attempt
entries so the diagnostic can detect an accidental post-revocation call.

The earlier synthetic process probe checked only a lease-service PID hard
kill. D2 additionally launched exact disposable Docker containers, killed
one synthetic runner process tree, pushed one new GitHub branch, observed A's
grant revocation after 4.357 seconds, and proved that a later A request did
not reach the provider while B still read successfully. It did not use a
real model or production service manager, and the broad token plus test-only
credential custody cannot satisfy the original scoped-identity gate. There
is no production agent-container route to the loopback endpoint. This remains
an integration draft, not a reason to lift #97's draft status or accept Q11.
After [amendment 12](AMENDMENT-12.md), grant revocation writes a separate
checkpoint before exact-container cleanup starts in a background thread.
Slow cleanup no longer stalls the lease scan, renewals or admission of another
run; tests hold cleanup open and exercise both. A 50-second use-time TTL plus
the 5-second heartbeat-loss threshold bounds a lost runner even if the lease
service's cleanup is slow. The reviewer-identified serial-cleanup and
replace-ref defects were not exercised in the earlier D2 live observation;
the corrected code needs fresh evidence. The probe accepts a fresh identity
and selected `GH_LAOMEDO` key without changing the historical observation.
The independent recheck then found an expensive Git classifier running inside
the shared SQLite write transaction. [Amendment 13](AMENDMENT-13.md) moves
classification outside that transaction, rechecks the grant before intent is
committed, and tests another lease renewal while classification is held open.
The heartbeat clock is read per lease; issue and renewal expiry are capped by
the last heartbeat plus 58 seconds. S3 grants only the first-slice Actions
run-list read rather than D2's diagnostic general REST read. The S3 probe
requires the `GH_LAOMEDO` key and an explicit selected-repository confirmation
before any provider contact; that confirmation must still be corroborated.
The run-scoped grant remains short-lived (less than 60 seconds), but a service
failure can leave it usable until expiry; the original live hard-kill and
credential-source acceptance tests remain required.

Review dependencies: merged specs #150, #250, #254 and #256; Laomedo #97 and
merged #103. A later frozen experiment must exercise the deployed mediated
path with a disposable *repository-scoped* GitHub identity before claiming
full acceptance. The broad-token diagnostic cannot substitute for that gate.
