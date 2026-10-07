# EXP-104 S5 protocol deviation: post-loss branch

Recorded: 2026-10-07, after the one-shot S5 run. This is a retrospective
validity record, not preregistration and not authorization for another run.
The frozen [live protocol](LIVE-PROTOCOL.md) requires the post-loss A write
to push a *new unique branch* using A's capability. The reviewed probe at
`6fc655cc4d96a09163ca544463fc4ea7f58a20bb` instead made a new
effect-ID request against A's existing approved branch
`exp104-s5-20261007-01-a`. The machine observation records HTTP 403
`grant_unavailable` and no additional provider call.

The same-branch request isolates revocation: before runner loss, A was
authorized for that exact branch, so a later refusal is not explained by
a wrong-branch check. Under the current exact-branch grant, a new branch
would be refused before reaching revocation logic. Nevertheless, the run
did not execute the protocol's literal new-branch case. Its internal
`scoped_candidate_pass` status is a harness result, not full EXP-104
protocol acceptance. Preserve the useful revocation evidence, but do not
count the new-branch acceptance criterion as met or promote drafts on it.

The protocol also requests monotonic host timestamps for loss, detection,
revocation, denial and remote read-back. S5 records the runner kill and
denial with monotonic values, but the lease service's detection/revocation
and cleanup are wall-clock values. The reported 4.552/4.556/9.657-second
service deltas are computed from recorded wall times on the same host, not
from a complete monotonic sequence. They are useful bounded diagnostic
measurements but not literal compliance with that timing-evidence rule.

Before any future live attempt, the protocol and branch-grant design need
an explicit reviewed reconciliation: either define the same-approved-branch
fresh-effect control as the intended revocation test, or design a grant
that legitimately permits a second distinct branch without weakening
unrelated branch restrictions. A future run needs its own frozen amendment,
fresh identity and separate authorization. S3's uncertain effect remains
`unknown`; S5 is consumed and must not be rerun.
