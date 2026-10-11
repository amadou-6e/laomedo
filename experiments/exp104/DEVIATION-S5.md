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
a wrong-branch check. This does not make the protocol's new-branch case
impossible. The mediator checks whether a grant is revoked **before** it
checks the branch: a new-branch request would return `push_branch_denied`
while A is active, but `grant_unavailable` after revocation. S5 did not
execute that literal new-branch case. Its internal
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

Before any future live attempt, explicitly decide whether the protocol
still requires its literal new-branch post-loss control. The current
mediator check order supports that case without a grant redesign; the
distinct error codes separate wrong-branch rejection from revoked-grant
rejection. A future run needs its own frozen amendment,
fresh identity and separate authorization. S3's uncertain effect remains
`unknown`; S5 is consumed and must not be rerun.
