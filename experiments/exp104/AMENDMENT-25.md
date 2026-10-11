# EXP-104 amendment 25: retire unexecuted S8 and freeze S9

Date: 2026-10-08. Frozen before S9 implementation is committed and before any
S9 provider call. S8 (`exp104-s8-20261008-01`) was pinned for review but
**never executed**. The independent reviewer disapproved its exact head
`a813219` because a clean checkout and reviewed SHA did not prove that Python
imported the reviewed `laomedo` modules. The reviewer also requested a local
synthetic Docker check of exact revocation and cleanup assertions. Because the
S8 source pin existed before this fix, S8 is retired rather than revised.

The fresh single-use identity is `exp104-s9-20261008-01`. Its only target is
`ga84jog/laomedo-exp104-disposable-20261007` (repository ID `1408647759`)
at baseline `1f1a505f2fbd31993a7946924a9bec5a27bb15c1`. New branches are
`exp104-s9-20261008-01-a` and `exp104-s9-20261008-01-b`. Abort if a branch
or PR marker already exists. Never retry an uncertain S7, S8 or S9 effect.

The sequence, four intended provider mutations, no-model limit and acceptance
criteria in amendments 21–24 apply with **S9 substituted for S8**. The user's
authorization and authoritative selected-repository-only token confirmation
carry forward; no extra scope proof is required. Independent positive review
of the final S9 head remains mandatory before the first provider write.

The S9 probe must refuse imported `laomedo` modules outside the reviewed clean
checkout before it reads the token. The host service and both runner processes
must start with that checkout as their working directory. Record the resolved
module root. The synthetic Windows Docker test must verify the exact revoked
grant and confirmed cleanup, without a provider token or model turn. Pin the
new code and test blobs in an S9 pre-run record after implementation. Any later
code, test or protocol change requires another fresh identity and review.
