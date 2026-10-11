# EXP-104 amendment 19: S6 literal new-branch control

Date: 2026-10-07. Status: frozen before S6 code changes or provider contact.
The user explicitly approved retaining the live protocol's new-branch
post-loss requirement and one fresh attempt, and confirmed that the
`GH_LAOMEDO` token selects only the authorized disposable repository.
This confirmation is recorded as user attestation, not independent access
to the token's GitHub settings. The earlier S3 uncertain effect stays
`unknown`; S5 and all older identities remain consumed.

Use one fresh identity `exp104-s6-20261007-01`, connection
`exp104-s6-selected-gh`, repository
`ga84jog/laomedo-exp104-disposable-20261007`, and new A/B/C run, lease,
container, branch and effect IDs. The distinct post-loss branch is
`exp104-s6-20261007-01-a-denied`. Before dispatch, require that the A,
B, C and denied refs do not exist. Keep the selected-token, baseline,
Actions-read and Git `push --dry-run` preflights. Stop on a failed or
uncertain preflight; do not automatically retry an unknown write.

After runner A is killed and its grant is durably revoked, make exactly
one `git_push` request for the *new* denied branch using A's original
capability, with a fresh effect ID and the same harmless marker commit.
Require HTTP 403 `grant_unavailable`, no added provider call, and an
independent remote-ref read-back confirming that the new branch is absent.
Before loss, the existing wrong-branch control must still return
`push_branch_denied`; this distinguishes the two checks. Leave A's
successfully created branch in place for review.

Record monotonic host timestamps for the runner kill, service detection,
revocation, denial and remote read-back. Extend the lease-service result
with monotonic detection/revocation/cleanup fields without removing the
existing wall-clock fields; test their order. If a cross-process monotonic
comparison is unavailable, mark the timing gate incomplete rather than
substituting wall-clock deltas. Check the exact container and process
cleanup, preserve sanitized raw observations and committed-byte hashes,
and use zero model turns. The run is single-use even if it fails. Do not
promote draft #97/#105 from a harness status alone; assess every frozen
protocol precondition and acceptance condition separately.

Governing specs are pinned to `amadou-6e/specs` merge commit
`21a7ae273e5a8bf2aff740dbea97a5b94fdb5432` (S5 evidence and open
Q02) and the previously merged account/mediation contracts. The exact
Laomedo implementation SHA must be recorded in the pre-run checkpoint.
