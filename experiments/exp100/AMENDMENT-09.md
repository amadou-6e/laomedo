# Prospective S10 pre-run review corrections

Before any S10 identity claim/capture. Review of executable `5bb0dbb` refused
execution for two validity gaps; no attempt ran. AMENDMENT-08 is retained.

Git refusal checks accept any nonzero native Git exit code, rather than an
unverified exact 1. The captured code remains visible. Forbidden targets must
still cause zero provider writes, with exactly two authorized push refspecs.
The gh exit codes remain exact (2 unsupported, 3 mediated refusal).

Add the omitted completed-run freeze control: direct freezer must return
run_grant_mismatch, HTTP mediation must remain unknown, and no new attempt
directory may appear. After revocation, attempt a new PR update and require
grant_unavailable before any provider call, as well as the existing read check.

To avoid confusing a scripted integration with a grant-expiry experiment,
the synthetic controller may renew the original grant for 60 seconds only
while independently inspecting this exact run/name/launch-token container
as owned and the fixture is still active. Check at most every 10 seconds,
capture elapsed renewal times, and stop renewing before completion controls.
Never resurrect an expired/revoked grant, change identity, issue a replacement
grant or claim this is production lease/service-manager survival evidence.
Failed renewal terminates this attempt without retry. Keep the 180-second
fixture wait bound, exact cleanup and no-model/local-provider scope.

The corrected executable must be committed and receive one focused independent
recheck covering both blockers before the single-use identity is executed.
