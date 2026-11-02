# EXP-104 amendment 24: replace unexecuted S7 with S8

Date: 2026-10-08. Frozen before any S8 provider call. S7
(`exp104-s7-20261007-01`) was pinned for review but **never executed**. The
independent pre-run reviewer disapproved its head `243b752` because a dirty
source tree could run under a reviewed SHA and because the negative PR update
did not first prove exact A-grant revocation. The installed-wheel CI test also
failed to import the experimental module from outside the checkout. Those
findings require code changes after S7's pre-run pin, so S7 is retired rather
than silently revised or reused.

The fresh single-use identity is `exp104-s8-20261008-01`. Its exact target is
only `ga84jog/laomedo-exp104-disposable-20261007` (repository ID
`1408647759`) at main baseline
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`. Its branches are
`exp104-s8-20261008-01-a` and `exp104-s8-20261008-01-b`; PR markers,
effect IDs, run IDs, leases and container names derive from this identity.
Abort if either branch or PR marker already exists. Never retry an uncertain
S7 or S8 effect.

The fixed sequence, four intended provider writes (two new-branch setup
pushes and two PR creates), post-loss PR-update denial, 60-second revocation
limit, B-continuity control, evidence requirements, and no-model limit in
[amendment 21](AMENDMENT-21.md) apply with **S8 substituted for S7**. The
capability-scan clarification in [amendment 22](AMENDMENT-22.md) also applies.
The user-authoritative `GH_LAOMEDO` selected-repository-only confirmation in
[amendment 23](AMENDMENT-23.md) carries forward; do not request additional
scope proof. The user's subsequent authorization covers the bounded S8 run,
but does not waive independent pre-run review of its exact source head.

The S8 probe must refuse a dirty source tree, verify exact A-grant revocation
**before** the negative update, require `grant_unavailable` afterwards, and
record exact A/B cleanup and container identity. It must pass the wheel test
outside the checkout. Pin the final code, test and protocol Git blobs in a
new S8 pre-run record, obtain an independent positive review at that exact
head, then execute **once**. A review that only covers S7 does not permit S8.

The no-model container retains the production Docker profile, including the
Codex profile volume, but runs `sleep`, not Codex. This test does not inspect
the volume's contents or establish general container secret safety. Agent
access to GitHub remains limited to the mediator capability; no reusable
GitHub token is mounted. The host service is outside the killed runner tree
for this test, but production OS service-manager installation and double
failure remain #93 work. Literal `git`/`gh` parity remains #100 work. No
model turn is consumed.
