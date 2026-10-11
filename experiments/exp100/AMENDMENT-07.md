# Prospective S10 candidate amendment: reviewed repeated-push safety

Recorded before implementation and before any S10 acceptance capture.
Governing selected native surface is specs merge
`d4dd27ae0e97c1f910ea5096be7c26ea2ece4b15`; original PROTOCOL-10 is unchanged.
The first candidate was reviewed at `308a75f`; no S10 identity has executed.

Reviewer found that an absent-ref-only second push becomes uncertain and
fences the branch. Add a trusted predecessor derived only from the run's
last confirmed branch-push result in the mediator journal. Confirm a
fast-forward in the same staged object database before obtaining a provider
credential, and push with compare-and-swap on that predecessor. The request
cannot nominate or override the predecessor. An unknown earlier effect
still blocks all new identities; a remote CAS mismatch remains unknown
after dispatch and is never automatically repeated. New runs do not inherit
another run's predecessor. No force/deletion/multiple-ref path is added.

Development controls will verify exact predecessor CAS, fast-forward
refusal before credential/provider contact, stored predecessor attribution,
and unchanged unknown-effect fencing. Add fixed handoff exclusion and
document stale-lock/capture handling without advising a new commit as a
way to bypass uncertainty. Fetch grant changes require the user's separate
read-scope decision; no new permission is inferred from this amendment.

No live provider call, model turn, permanent service installation or S10
acceptance execution follows from this amendment. A separately frozen,
independently reviewed executable capture remains required.
