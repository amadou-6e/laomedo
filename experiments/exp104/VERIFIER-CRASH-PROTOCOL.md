# Credential-free verifier worker-loss diagnostic

Prospective freeze 2026-10-09, before executable diagnostic implementation.
Identity `exp104-verifier-loss-s1-20261009`. Tests draft ownership/reconciliation
implementation, not real agent, run grants or GitHub. The existing implementation
is not preregistered experimental code; this protocol freezes the new probe's
case and outcome rules before its implementation/run.

## Case and controls

Build a disposable local Git baseline/candidate and active trusted run record
with synthetic container/grant identity. Freeze the exact bundle once. Launch
one worker using production BundleVerifier/verify_frozen_bundle against the
pinned network-disabled non-root Git-object image
`sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.
The probe's export hook pauses before reading bytes, after production stage
verification and durable ownership reservation, and signals a ready file.
This instrumentation is deliberate; no production verification logic is
replaced. Kill this exact worker tree once after readiness, before export.

Read ownership and independently inspect the exact stage. The stage must still
exist to establish the orphan. Start a new worker scan using unchanged frozen
attempt/claim; it may only inspect/remove, not create/start or retry verification.
Wait at most 20 seconds for an `orphan-cleanup.json` verified removal and exact
container absence. Original `verification.json` must remain unknown, never
become verified after crash, and original persistent claim must remain.

Negative control: a separately named, labelled same-prefix container stays
alive across cleanup and is removed only by the probe's exact-ID cleanup after
all assertions. Zero provider requests/grants/model turns. One main worker
launch and one kill; no repeat after uncertain effects. Any startup/readiness
failure consumes the identity without proving crash cleanup. No privilege
elevation, fallback image or uncertain stage re-dispatch.

## Evidence and safety

Machine capture source SHA, fixture/bundle hashes, reservation-before-dispatch
check, exact IDs/names/labels, before/after stage state, original journal status,
claim preservation, cleanup report and negative-control state. No credential,
user paths or raw Git/Docker logs committed. Private roots outside Git and agent
mounts. Use no network, read-only rootfs, non-root, dropped capabilities, PID/
memory limits for both containers; no sensitive mounts. Finally inspect exact
IDs/labels again and remove only owned stage/control. Preserve cleanup failures
as unknown; never delete by prefix.

Independent pre-run review of exact probe/source is mandatory. Positive result
supports only restarting a credential-free worker after a crash at the declared
pause; it is not scheduler failure/power-loss cleanup, orphan expiry while no
worker lives, real-model/Q11 acceptance or full draft #105/#97 readiness.
